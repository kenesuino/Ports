"""Port snapshot collection and session attribution (pure, headless).

Windows listeners come from psutil.net_connections; ownership is resolved
against each session's Job Object / process tree. External listeners are
everything left over after a configurable noise filter.

Owner identity = environment + PID + process start time, so a recycled PID
can never be confused with the original owner.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

import psutil

LOCALHOST_NAMES = {"127.0.0.1", "::1", "0.0.0.0", "::"}

# Windows-side forwarders for WSL localhost forwarding; their sockets are
# duplicates of Linux listeners, not independent owners.
WSL_FORWARDERS = {"wslrelay.exe", "wslhost.exe", "wsl.exe"}

PROTECTED_NAMES = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe", "dwm.exe",
    "idle", "system idle process",
}


@dataclass(frozen=True)
class OwnerIdentity:
    env: str          # "windows" | "wsl"
    pid: int
    create_time: float
    name: str = ""
    distro: str = ""  # set when env == "wsl"

    def key(self) -> tuple:
        return (self.env, self.distro, self.pid, self.create_time)


@dataclass
class Listener:
    address: str      # e.g. "127.0.0.1", "::", "0.0.0.0"
    port: int
    owner: OwnerIdentity | None  # None => inaccessible/unknown
    env: str = "windows"
    distro: str = ""

    @property
    def is_wildcard(self) -> bool:
        return self.address in ("0.0.0.0", "::")

    @property
    def display(self) -> str:
        return f":{self.port}"


@dataclass
class PortSnapshot:
    # session_id -> [Listener]
    session_ports: dict = field(default_factory=dict)
    # external listeners (post-filter)
    external: list = field(default_factory=list)
    # owners we could not inspect
    unknown: list = field(default_factory=list)


def is_localhost(addr: str) -> bool:
    if addr in LOCALHOST_NAMES:
        return True
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def windows_owner(pid: int) -> OwnerIdentity | None:
    if not pid or pid <= 0:
        return None
    try:
        p = psutil.Process(pid)
        return OwnerIdentity("windows", pid, p.create_time(), p.name())
    except psutil.Error:
        return None


def collect_windows_listeners() -> list[Listener]:
    out = []
    try:
        conns = psutil.net_connections(kind="tcp")
    except psutil.Error:
        return out
    for c in conns:
        if c.status != psutil.CONN_LISTEN or not c.laddr:
            continue
        addr = c.laddr.ip
        if not is_localhost(addr):
            continue
        out.append(Listener(addr, c.laddr.port, windows_owner(c.pid)))
    return out


def filter_noise(listener: Listener, denylist: list[str],
                 allowlist: list[str]) -> bool:
    """True => keep in external panel. Only affects presentation."""
    name = (listener.owner.name if listener.owner else "").lower()
    if name and name in {a.lower() for a in allowlist}:
        return True
    if name and name in {d.lower() for d in denylist}:
        return False
    if name in PROTECTED_NAMES:
        return False
    return True


def map_ports(session_members: dict[str, set[int]],
              listeners: list[Listener],
              session_roots: dict[str, int] | None = None) -> tuple[dict, list]:
    """Attribute listeners to sessions by PID membership.

    Returns (session_id -> [Listener], unattributed [Listener]).
    A session's own shell PID never counts as an owner match for attribution
    purposes unless it literally holds the socket.
    """
    roots = session_roots or {}
    attributed: dict[str, list[Listener]] = {sid: [] for sid in session_members}
    rest: list[Listener] = []
    for lst in listeners:
        owner_pid = lst.owner.pid if lst.owner else None
        sid_hit = None
        if owner_pid is not None:
            for sid, members in session_members.items():
                if owner_pid in members or owner_pid == roots.get(sid):
                    sid_hit = sid
                    break
        if sid_hit:
            attributed[sid_hit].append(lst)
        else:
            rest.append(lst)
    return attributed, rest


def merge_wsl_forwarders(windows_listeners: list[Listener],
                         wsl_ports: dict[str, list[Listener]]
                         ) -> list[Listener]:
    """Drop Windows forwarder sockets whose port is already reported by a
    WSL session helper - they are duplicates, not independent owners."""
    wsl_port_set = {l.port for lst in wsl_ports.values() for l in lst}
    out = []
    for l in windows_listeners:
        name = l.owner.name.lower() if l.owner else ""
        if name in WSL_FORWARDERS and l.port in wsl_port_set:
            continue
        out.append(l)
    return out
