"""Strict, versioned workspace definitions separate from running processes."""
from dataclasses import dataclass, field, asdict
import hashlib
import json
import re
import uuid

ACCENTS = ("#e7e7e7", "#b4b4b4", "#8e8e8e", "#d9a441", "#4fd18b", "#ff7b8a")
_ACCENT_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def valid_accent(value: str) -> bool:
    """Accept any hex accent so profiles saved with older palettes still load."""
    return bool(_ACCENT_RE.match(value or ""))


def identifier(value=None):
    if value is None:
        return uuid.uuid4().hex
    if not isinstance(value, str):
        raise ValueError("ID must be a UUID string")
    return uuid.UUID(value).hex


def text(value, limit=4096):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise ValueError("Invalid or oversized text field")
    return value


@dataclass
class TerminalProfile:
    id: str = field(default_factory=identifier)
    name: str = "Terminal"
    shell: str = "pwsh"
    cwd: str = ""
    startup_cmd: str = ""
    restart_cmd: str = ""
    distro: str = ""
    accent: str = ACCENTS[0]
    expected_ports: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Terminal must be an object")
        result = cls(id=identifier(data.get("id")))
        for key in ("name", "shell", "cwd", "startup_cmd", "restart_cmd", "distro", "accent"):
            setattr(result, key, text(data.get(key, getattr(result, key)), 120 if key in ("name", "distro") else 4096))
        if not result.name or result.shell not in ("pwsh", "powershell", "cmd", "wsl") or not valid_accent(result.accent):
            raise ValueError("Invalid terminal name, shell, or accent")
        ports = data.get("expected_ports", [])
        if not isinstance(ports, list) or len(ports) > 64 or any(type(p) is not int or not 1 <= p <= 65535 for p in ports):
            raise ValueError("Expected ports must be integers 1–65535")
        result.expected_ports = list(dict.fromkeys(ports))
        return result


@dataclass
class WorkspaceProfile:
    id: str = field(default_factory=identifier)
    name: str = "Workspace"
    terminals: list = field(default_factory=list)
    revision: int = 1
    reviewed_fingerprint: str = ""

    def execution_fingerprint(self):
        content = [{key: getattr(t, key) for key in ("id", "shell", "distro", "cwd", "startup_cmd", "restart_cmd")} for t in self.terminals]
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()

    def needs_review(self):
        return self.reviewed_fingerprint != self.execution_fingerprint()

    def approve(self):
        self.reviewed_fingerprint = self.execution_fingerprint()

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Workspace must be an object")
        raw = data.get("terminals", [])
        if not isinstance(raw, list) or not 1 <= len(raw) <= 32:
            raise ValueError("Workspace requires 1–32 terminals")
        terminals = [TerminalProfile.from_dict(t) for t in raw]
        if len({t.id for t in terminals}) != len(terminals):
            raise ValueError("Duplicate terminal ID")
        revision = data.get("revision", 1)
        if type(revision) is not int or not 1 <= revision <= 1000000:
            raise ValueError("Invalid profile revision")
        name = text(data.get("name", "Workspace"), 120)
        if not name.strip():
            raise ValueError("Workspace name is empty")
        return cls(identifier(data.get("id")), name, terminals, revision,
                   text(data.get("reviewed_fingerprint", ""), 64))
