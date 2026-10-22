"""Versioned config with atomic writes and explicit corrupt-file recovery."""
from dataclasses import dataclass, field, asdict
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

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
    terminal_font_size: int = 13
    copy_on_select: bool = True
    rail_collapsed: bool = False
    external_group_open: bool = False
    workspace_panel_visible: bool = True
    workspace_panel_width: int = 240
    restore_layout: bool = True
    probe_interval: int = 5
    geometry: str = ""
    splitter: str = ""
    view_mode: str = "sidebar"
    reduced_motion: str = "system"
    loaded_workspace_ids: list | None = None
    expanded_workspace_ids: list = field(default_factory=list)
    selected_workspace_id: str = '@other'
    left_sidebar_width: int = 260
    ports_inspector_visible: bool = True
    ports_inspector_width: int = 280
    managed_ports_scope: str = 'selected'
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
        try:
            font_size = int(data.get("terminal_font_size", 13))
            config.terminal_font_size = max(9, min(20, font_size))
        except (TypeError, ValueError):
            config.terminal_font_size = 13
        config.rail_collapsed = bool(data.get("rail_collapsed", False))
        config.copy_on_select = bool(data.get("copy_on_select", True))
        config.external_group_open = bool(data.get("external_group_open", False))
        config.workspace_panel_visible = bool(
            data.get("workspace_panel_visible", True))
        try:
            panel_width = int(data.get("workspace_panel_width", 240))
        except (TypeError, ValueError):
            panel_width = 240
        config.workspace_panel_width = max(180, min(420, panel_width))
        config.restore_layout = bool(data.get("restore_layout", True))
        try:
            probe_interval = int(data.get("probe_interval", 5))
        except (TypeError, ValueError):
            probe_interval = 5
        config.probe_interval = max(2, min(60, probe_interval))
        for key in ("geometry", "splitter"):
            setattr(config, key, text(data.get(key, ""), 65536))
        # `view_mode` is accepted for compatibility with older configs, then
        # discarded: tabs are the only navigation model.
        if data.get("view_mode", "tabs") not in ("sidebar", "tabs"):
            raise ValueError("Invalid legacy view mode")
        config.view_mode = "tabs"
        known = {p.id for p in config.profiles}
        raw_loaded = data.get('loaded_workspace_ids')
        if raw_loaded is None:
            raw_loaded = [p.id for p in config.profiles]
            raw_loaded += [s.workspace_profile_id for s in config.saved_sessions if s.workspace_profile_id]
        def ids(value):
            if not isinstance(value, list) or len(value) > 128 or any(not isinstance(v, str) for v in value):
                raise ValueError('Invalid workspace navigation IDs')
            return list(dict.fromkeys(value))
        requested = ids(raw_loaded)
        config.loaded_workspace_ids = [v for v in requested if v in known]
        if any(v not in known for v in requested):
            config.warning = 'Some remembered workspaces no longer exist and were removed from navigation.'
        config.expanded_workspace_ids = [v for v in ids(data.get('expanded_workspace_ids', config.loaded_workspace_ids)) if v in known or v == '@other']
        selected = data.get('selected_workspace_id', '@other')
        if not isinstance(selected, str):
            raise ValueError('Invalid selected workspace')
        config.selected_workspace_id = selected if selected in known else '@other'
        for key, fallback, minimum, maximum in (
            ('left_sidebar_width', 260, 220, 420),
            ('ports_inspector_width', config.workspace_panel_width, 220, 420)):
            value = data.get(key, fallback)
            if type(value) is not int:
                raise ValueError(f'Invalid {key}')
            setattr(config, key, max(minimum, min(maximum, value)))
        config.ports_inspector_visible = data.get('ports_inspector_visible', config.workspace_panel_visible)
        if type(config.ports_inspector_visible) is not bool:
            raise ValueError('Invalid inspector visibility')
        config.managed_ports_scope = data.get('managed_ports_scope', 'selected')
        if config.managed_ports_scope not in ('selected', 'all'):
            raise ValueError('Invalid ports scope')
        config.rail_collapsed = False
        config.restore_layout = False
        config.reduced_motion = data.get("reduced_motion", "system")
        if config.reduced_motion not in ("system", "on", "off"):
            raise ValueError("Invalid motion setting")
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        config = Config(warning=f"Config retained for recovery: {exc}", read_only=True)
    return config


def save(config):
    if config.read_only:
        config.last_error = "Recovery required; original config retained"
        return False
    data = {key: getattr(config, key) for key in ("port_labels", "process_denylist", "process_allowlist", "scrollback_lines", "terminal_font_size", "copy_on_select", "rail_collapsed", "external_group_open", "workspace_panel_visible", "workspace_panel_width", "restore_layout", "probe_interval", "reduced_motion", "geometry", "splitter")}
    data.update({key: getattr(config, key) for key in ('loaded_workspace_ids', 'expanded_workspace_ids', 'selected_workspace_id', 'left_sidebar_width', 'ports_inspector_visible', 'ports_inspector_width', 'managed_ports_scope')})
    data['loaded_workspace_ids'] = config.loaded_workspace_ids if config.loaded_workspace_ids is not None else [p.id for p in config.profiles]
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
