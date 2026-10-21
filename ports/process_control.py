"""Identity-safe process control for Windows; WSL signals go through helper.

Every destructive action revalidates PID + create_time immediately before
acting. Protected system processes and unknown owners are refused.
"""

from __future__ import annotations

import re
import os
import time
from dataclasses import dataclass

import psutil

from .port_monitor import OwnerIdentity, PROTECTED_NAMES

# crude credential scrub for displayed command lines
_SECRET_RE = re.compile(
    r"(?i)(--?(?:password|passwd|token|secret|api[-_]?key|auth)"
    r"[=\s])\S+")


def redact_cmdline(cmdline: list[str] | str) -> str:
    text = " ".join(cmdline) if isinstance(cmdline, list) else str(cmdline)
    return _SECRET_RE.sub(r"\1***", text)


@dataclass
class KillResult:
    ok: bool
    message: str


def _identity_matches(proc: psutil.Process, owner: OwnerIdentity) -> bool:
    try:
        return proc.pid == owner.pid and \
            proc.create_time() == owner.create_time
    except psutil.Error:
        return False


def describe_target(owner: OwnerIdentity) -> dict:
    """Details for the confirmation dialog; empty strings when inaccessible."""
    info = {"pid": owner.pid, "name": owner.name, "cmdline": "",
            "create_time": owner.create_time, "env": owner.env,
            "distro": owner.distro}
    try:
        p = psutil.Process(owner.pid)
        if _identity_matches(p, owner):
            info["name"] = p.name()
            try:
                info["cmdline"] = redact_cmdline(p.cmdline())
            except psutil.Error:
                pass
    except psutil.Error:
        pass
    return info


def kill_windows(owner: OwnerIdentity, force_after: float = 3.0, *,
                 port=None, address=None, protected_pids=()) -> KillResult:
    """Force terminate only verified identity, optionally current socket owner."""
    if owner.env != "windows" or owner.pid <= 4 or owner.pid == os.getpid() or owner.pid in protected_pids:
        return KillResult(False, "refusing protected or invalid process target")
    name = owner.name.lower()
    if name in PROTECTED_NAMES:
        return KillResult(False, f"refusing to kill protected process {name}")
    try:
        proc = psutil.Process(owner.pid)
    except psutil.NoSuchProcess:
        return KillResult(False, "process already exited")
    except psutil.Error as e:
        return KillResult(False, f"cannot access process: {e}")
    if not _identity_matches(proc, owner):
        return KillResult(False, "process identity changed (PID reused); aborted")
    if proc.name().lower() in PROTECTED_NAMES:
        return KillResult(False, "refusing protected process")
    if port is not None:
        try:
            current = [c for c in psutil.net_connections(kind="tcp")
                       if c.status == psutil.CONN_LISTEN and c.laddr and c.pid == owner.pid
                       and c.laddr.port == port and (address is None or c.laddr.ip == address)]
        except psutil.Error as exc:
            return KillResult(False, f"Cannot revalidate socket: {exc}")
        if not current or not _identity_matches(proc, owner):
            return KillResult(False, "socket ownership changed; aborted")
    try:
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return KillResult(False, "process already exited")
        proc.terminate()
    except psutil.NoSuchProcess:
        return KillResult(True, "process already exited")
    except psutil.AccessDenied:
        return KillResult(False, "access denied (process may be elevated)")
    except psutil.Error as e:
        return KillResult(False, str(e))
    try:
        proc.wait(timeout=force_after)
        return KillResult(True, "terminated")
    except psutil.TimeoutExpired:
        try:
            if not _identity_matches(proc, owner):
                return KillResult(False, "identity changed before force kill")
            proc.kill()
            proc.wait(timeout=2)
            return KillResult(True, "force-killed")
        except psutil.NoSuchProcess:
            return KillResult(True, "terminated")
        except psutil.Error as e:
            return KillResult(False, f"force kill failed: {e}")


def current_owner_of_port(port: int) -> OwnerIdentity | None:
    """Who listens on this localhost port right now (identity re-check)."""
    try:
        conns = psutil.net_connections(kind="tcp")
    except psutil.Error:
        return None
    for c in conns:
        if c.status == psutil.CONN_LISTEN and c.laddr and \
                c.laddr.port == port and c.pid:
            try:
                p = psutil.Process(c.pid)
                return OwnerIdentity("windows", c.pid, p.create_time(), p.name())
            except psutil.Error:
                return None
    return None
