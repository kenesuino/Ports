"""Validated, versioned JSON persistence under %APPDATA%/Ports.

Stores port labels, external-port filters, saved sessions, and UI prefs.
Atomic writes preserve the prior config on failure; malformed config is
retained for recovery rather than overwritten.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1
MAX_SESSIONS = 64
MAX_LABEL_LEN = 120
MAX_CMD_LEN = 1024
MAX_FILTER_ENTRIES = 256

DEFAULT_PROCESS_DENYLIST = [
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe",
    "dwm.exe", "spoolsv.exe", "searchhost.exe", "sihost.exe",
    "fontdrvhost.exe", "memory compression",
]

_SAFE_NAME = re.compile(r"^[\w .\-\[\]\(\)@]+$")


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Ports"


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class SavedSession:
    name: str
    shell: str          # pwsh | powershell | cmd | wsl
    cwd: str
    startup_cmd: str = ""
    distro: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name, "shell": self.shell, "cwd": self.cwd,
            "startup_cmd": self.startup_cmd, "distro": self.distro,
        }

    @staticmethod
    def from_dict(d: dict) -> "SavedSession":
        shell = str(d.get("shell", "pwsh"))
        if shell not in ("pwsh", "powershell", "cmd", "wsl"):
            shell = "pwsh"
        return SavedSession(
            name=str(d.get("name", "Terminal"))[:MAX_LABEL_LEN] or "Terminal",
            shell=shell,
            cwd=str(d.get("cwd", ""))[:MAX_CMD_LEN],
            startup_cmd=str(d.get("startup_cmd", ""))[:MAX_CMD_LEN],
            distro=str(d.get("distro", ""))[:MAX_LABEL_LEN],
        )


@dataclass
class Config:
    port_labels: dict = field(default_factory=dict)   # "shell:port" -> label
    process_denylist: list = field(default_factory=lambda: list(DEFAULT_PROCESS_DENYLIST))
    process_allowlist: list = field(default_factory=list)
    saved_sessions: list = field(default_factory=list)  # list[SavedSession]
    scrollback_lines: int = 10000
    geometry: bytes | None = None
    splitter: bytes | None = None

    def label_key(self, scope: str, port: int) -> str:
        return f"{scope}:{port}"

    def get_label(self, scope: str, port: int) -> str:
        return self.port_labels.get(self.label_key(scope, port), "")

    def set_label(self, scope: str, port: int, label: str) -> None:
        key = self.label_key(scope, port)
        label = label.strip()[:MAX_LABEL_LEN]
        if label:
            self.port_labels[key] = label
        else:
            self.port_labels.pop(key, None)


def _validate_filters(lst, default) -> list:
    if not isinstance(lst, list):
        return list(default)
    out = []
    for item in lst[:MAX_FILTER_ENTRIES]:
        s = str(item).strip().lower()
        if s and _SAFE_NAME.match(s):
            out.append(s)
    return out


def load() -> Config:
    """Load config; on any failure return defaults without touching the file."""
    path = config_path()
    cfg = Config()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
            return cfg
        labels = data.get("port_labels", {})
        if isinstance(labels, dict):
            cfg.port_labels = {
                str(k)[:MAX_CMD_LEN]: str(v)[:MAX_LABEL_LEN]
                for k, v in list(labels.items())[:1024]
            }
        cfg.process_denylist = _validate_filters(
            data.get("process_denylist"), DEFAULT_PROCESS_DENYLIST)
        cfg.process_allowlist = _validate_filters(data.get("process_allowlist"), [])
        sessions = data.get("saved_sessions", [])
        if isinstance(sessions, list):
            cfg.saved_sessions = [
                SavedSession.from_dict(s) for s in sessions[:MAX_SESSIONS]
                if isinstance(s, dict)
            ]
        try:
            sb = int(data.get("scrollback_lines", 10000))
            cfg.scrollback_lines = max(100, min(100000, sb))
        except (TypeError, ValueError):
            pass
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return cfg


def save(cfg: Config) -> bool:
    """Atomically write config. Returns False on failure; prior file preserved."""
    path = config_path()
    data = {
        "version": SCHEMA_VERSION,
        "port_labels": cfg.port_labels,
        "process_denylist": cfg.process_denylist,
        "process_allowlist": cfg.process_allowlist,
        "saved_sessions": [s.to_dict() for s in cfg.saved_sessions[:MAX_SESSIONS]],
        "scrollback_lines": cfg.scrollback_lines,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            shutil.move(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    except OSError:
        return False
