"""Versioned config with atomic writes and explicit corrupt-file recovery."""
from dataclasses import dataclass, field, asdict
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid

from .profiles import WorkspaceProfile, identifier, text, ACCENTS

SCHEMA_VERSION = 2
MAX_SESSIONS = 64
MAX_LABEL_LEN = 120
DEFAULT_PROCESS_DENYLIST = ["system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe", "dwm.exe", "spoolsv.exe", "searchhost.exe", "sihost.exe", "fontdrvhost.exe", "memory compression"]


def config_dir():
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "Ports"


def config_path():
    return config_dir() / "config.json"


@dataclass
class SavedSession:
    name: str
    shell: str
    cwd: str
    startup_cmd: str = ""
    distro: str = ""
    id: str = field(default_factory=identifier)
    restart_cmd: str = ""
    workspace_profile_id: str = ""
    terminal_profile_id: str = ""
    instance_id: str = ""
    accent: str = ACCENTS[0]

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        if not isinstance(data, dict):
            raise ValueError("Invalid saved terminal")
        shell = data.get("shell", "pwsh")
        if shell not in ("pwsh", "powershell", "cmd", "wsl"):
            shell = "pwsh"  # legacy config compatibility
        result = SavedSession(text(data.get("name", "Terminal"), 120), shell, text(data.get("cwd", "")))
        for key in ("startup_cmd", "restart_cmd", "distro", "workspace_profile_id", "terminal_profile_id", "instance_id", "accent"):
            if key in data:
                setattr(result, key, text(data[key]))
        result.id = identifier(data.get("id"))
        if result.accent not in ACCENTS:
            result.accent = ACCENTS[0]
        return result


@dataclass
class Config:
    port_labels: dict = field(default_factory=dict)
    process_denylist: list = field(default_factory=lambda: list(DEFAULT_PROCESS_DENYLIST))
    process_allowlist: list = field(default_factory=list)
    saved_sessions: list = field(default_factory=list)
    profiles: list = field(default_factory=list)
    scrollback_lines: int = 10000
    geometry: str = ""
    splitter: str = ""
    view_mode: str = "sidebar"
    reduced_motion: str = "system"
    warning: str = ""
    last_error: str = ""
    read_only: bool = False

    def label_key(self, scope, port):
        return f"{scope}:{port}"

    def get_label(self, scope, port):
        return self.port_labels.get(self.label_key(scope, port), "")

    def set_label(self, scope, port, label):
        key = self.label_key(scope, port)
        label = label.strip()[:120]
        if label:
            self.port_labels[key] = label
        else:
            self.port_labels.pop(key, None)


def load():
    config = Config()
    path = config_path()
    try:
        if not path.exists():
            return config
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Config exceeds 2 MiB")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") not in (1, 2):
            raise ValueError("Unsupported config version")
        for key in ("process_denylist", "process_allowlist"):
            values = data.get(key, getattr(config, key))
            if not isinstance(values, list) or len(values) > 256 or any(not isinstance(v, str) or len(v) > 120 for v in values):
                raise ValueError(f"Invalid {key}")
            setattr(config, key, [v.strip().lower() for v in values if v.strip()])
        labels = data.get("port_labels", {})
        if not isinstance(labels, dict) or len(labels) > 4096:
            raise ValueError("Invalid labels")
        config.port_labels = {text(k): text(v, 120) for k, v in labels.items()}
        saved = data.get("saved_sessions", [])
        if not isinstance(saved, list) or len(saved) > MAX_SESSIONS:
            raise ValueError("Invalid saved sessions")
        config.saved_sessions = [SavedSession.from_dict(s) for s in saved if isinstance(s, dict)]
        profiles = data.get("profiles", [])
        if not isinstance(profiles, list) or len(profiles) > 128:
            raise ValueError("Invalid workspace count")
        config.profiles = [WorkspaceProfile.from_dict(p) for p in profiles]
        if len({p.id for p in config.profiles}) != len(config.profiles):
            raise ValueError("Duplicate workspace IDs")
        lines = data.get("scrollback_lines", 10000)
        if type(lines) is not int or not 100 <= lines <= 100000:
            raise ValueError("Invalid scrollback limit")
        config.scrollback_lines = lines
        for key in ("geometry", "splitter"):
            setattr(config, key, text(data.get(key, ""), 65536))
        config.view_mode = data.get("view_mode", "sidebar")
        config.reduced_motion = data.get("reduced_motion", "system")
        if config.view_mode not in ("sidebar", "tabs") or config.reduced_motion not in ("system", "on", "off"):
            raise ValueError("Invalid navigation/motion setting")
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        config = Config(warning=f"Config retained for recovery: {exc}", read_only=True)
    return config


def save(config):
    if config.read_only:
        config.last_error = "Recovery required; original config retained"
        return False
    data = {key: getattr(config, key) for key in ("port_labels", "process_denylist", "process_allowlist", "scrollback_lines", "view_mode", "reduced_motion", "geometry", "splitter")}
    data.update(version=SCHEMA_VERSION, saved_sessions=[s.to_dict() for s in config.saved_sessions], profiles=[p.to_dict() for p in config.profiles])
    temporary = None
    try:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        config.last_error = ""
        return True
    except (OSError, ValueError, TypeError) as exc:
        config.last_error = str(exc)
        return False
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def recover(config):
    try:
        source = config_path()
        if source.exists():
            shutil.copy2(source, source.with_suffix(f".recovery-{time.time_ns()}.json"))
        config.read_only = False
        config.warning = ""
        return True
    except OSError as exc:
        config.last_error = str(exc)
        return False
