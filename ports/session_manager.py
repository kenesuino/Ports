"""Persistent sessions and workspace instances with explicit command readiness."""
from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .config_store import SavedSession
from .pty_session import PtySession, available_shells
from .shell_protocol import PromptParser
from .terminal_view import TerminalView
from .workspace_navigation import SessionAge
from .wsl_backend import WslBackend

HOOKS = Path(__file__).parent / "shell_integration"


def linux_path(path: Path) -> str:
    text = str(path.resolve())
    return "/mnt/" + text[0].lower() + text[2:].replace("\\", "/")


class TerminalSession(QObject):
    changed = pyqtSignal()
    exited = pyqtSignal()
    promptReceived = pyqtSignal(str)
    startFinished = pyqtSignal(str)
    view_factory = None

    def __init__(self, name, shell, cwd, startup_cmd="", distro="",
                 scrollback=10000, parent=None):
        super().__init__(parent)
        self.id = uuid.uuid4().hex
        self.definition_id = uuid.uuid4().hex
        self.profile_id = ""
        self.instance_id = ""
        self.name, self.shell, self.cwd = name, shell, cwd
        self.startup_cmd, self.restart_cmd = startup_cmd, startup_cmd
        self.distro = distro
        self.accent = "#e6e9ee"
        self.expected_ports = []
        self.age = SessionAge()
        self.state = "starting"
        self.current_cwd = ""
        self.last_error = ""
        self.child_name = ""
        self.children = []
        self.listeners = []
        self.pty = None
        self.view = None
        self.wsl = None
        self.wsl_shell_pid = None
        self._pidfile = f"/tmp/ports-{self.id}.pid"
        self._closed = threading.Event()
        self._startup_pending = bool(startup_cmd)
        self._restart_pending = False
        self._restart_command = ""
        self._prompt_seen = False
        self._token = uuid.uuid4().hex
        self._parser = PromptParser(self._token)
        self._worker = None
        self._scrollback = scrollback
        self.promptReceived.connect(self._on_prompt)
        self.startFinished.connect(self._started)
        self.exited.connect(self._mark_exited)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._timed_out)

    @property
    def label_scope(self):
        return f"profile/{self.profile_id}/{self.definition_id}" if self.profile_id else self.definition_id

    def start(self, scrollback=10000, asynchronous=False):
        if self._closed.is_set():
            return
        if self.view is None:
            factory = type(self).view_factory or TerminalView
            self.view = factory(scrollback=scrollback)
            self.view.inputReceived.connect(self._on_input)
            self.view.resizeReceived.connect(self._on_resize)
        self.state, self.last_error = "starting", ""
        self._deadline.start(30000)
        if asynchronous:
            self._worker = threading.Thread(target=self._spawn_worker, daemon=True)
            self._worker.start()
        else:
            self._spawn_worker()

    def prepare_close(self):
        """Release GUI-owned resources on GUI thread before worker cleanup."""
        self._deadline.stop()
        self._startup_pending = self._restart_pending = False
        if self.view:
            self.view.shutdown()

    def _spawn_worker(self):
        try:
            if self.shell not in available_shells():
                raise RuntimeError(f"Shell unavailable: {self.shell}")
            if self.shell != "wsl" and self.cwd and not os.path.isdir(self.cwd):
                raise RuntimeError(f"Folder not found: {self.cwd}")
            if self._closed.is_set():
                return
            pty = PtySession(self.shell, cwd=self.cwd, distro=self.distro,
                             on_data=self._on_pty_data, on_exit=self._on_exit)
            if self.shell in ("pwsh", "powershell"):
                pty.launch_args = ["-NoLogo", "-NoExit", "-File",
                                   str(HOOKS / "powershell.ps1"), self._token]
            elif self.shell == "wsl":
                distro_args = ["-d", self.distro] if self.distro else []
                check = subprocess.run(["wsl", *distro_args, "--", "bash", "-c",
                                        'command -v python3 && command -v ss && test -d ' + shlex.quote(self.cwd or '/tmp')],
                                       capture_output=True, timeout=20)
                if check.returncode:
                    raise RuntimeError("WSL folder unavailable or python3/iproute2 missing")
                hook = shlex.quote(linux_path(HOOKS / "bash.sh"))
                # Normalize CRLF in-memory: Windows editors can rewrite shell
                # assets even when repository eol attributes request LF.
                init_path = f'/tmp/ports-hook-{self.id}.sh'
                cd = "cd -- " + shlex.quote(self.cwd) if self.cwd else 'cd -- "$HOME"'
                command = (f"umask 077; {cd} || exit; echo $$ > {self._pidfile}; "
                           f"export PORTS_TOKEN={self._token}; "
                           f"tr -d '\\r' < {hook} > {init_path}; "
                           f"exec bash --rcfile {init_path} -i")
                pty._wsl_command = ["bash", "-c", command]
            else:
                # A custom prompt sentinel provides initial CMD readiness.
                # Later restarts remain explicit-confirmation because CMD has
                # no reliable foreground-command lifecycle hook.
                marker = f"$E]777;ports;{self._token};ready;\x07"
                pty.launch_args = ["/Q", "/K", f"prompt {marker}$P$G"]
            self.pty = pty
            pty.start()
            self.age.start()
            if self._closed.is_set():
                pty.close()
                return
            self.startFinished.emit("")
            if self.shell == "wsl":
                self._start_wsl_backend()
        except Exception as exc:
            self.startFinished.emit(str(exc))

    def _started(self, error):
        if self._closed.is_set():
            return
        if error:
            self.state, self.last_error = "failed", error
            self._deadline.stop()
        self.changed.emit()

    def _start_wsl_backend(self):
        args = ["-d", self.distro] if self.distro else []
        for _ in range(30):
            if self._closed.wait(0.2):
                return
            try:
                result = subprocess.run(["wsl", *args, "--", "cat", self._pidfile],
                                        capture_output=True, text=True, timeout=3)
                if not result.stdout.strip().isdigit():
                    continue
                self.wsl_shell_pid = int(result.stdout.strip())
                backend = WslBackend(self.distro, self.wsl_shell_pid)
                if backend.start():
                    if self._closed.is_set():
                        backend.close()
                    else:
                        self.wsl = backend
                else:
                    self.last_error = backend.last_error
                self.changed.emit()
                return
            except (OSError, subprocess.TimeoutExpired):
                continue
        self.last_error = "WSL helper could not identify shell; tracking unavailable"
        self.changed.emit()

    def _on_pty_data(self, data):
        clean, prompts = self._parser.feed(data)
        if clean and self.view:
            self.view.feed(clean)
        for cwd in prompts:
            self.promptReceived.emit(cwd)

    def _on_prompt(self, cwd):
        if self._closed.is_set():
            return
        self._prompt_seen = True
        if cwd:
            self.current_cwd = cwd
        self._deadline.stop()
        self.state = "ready"
        if self._startup_pending:
            self._startup_pending = False
            self._execute(self.startup_cmd)
        elif self._restart_pending and self.shell != "cmd":
            command = self._restart_command
            self._restart_pending = False
            self._execute(command)
        self.changed.emit()

    def _execute(self, command):
        if self.pty and not self._closed.is_set() and command:
            self.state = "running"
            self.pty.write(command + "\r")

    def _on_input(self, text):
        if self._closed.is_set():
            return
        # xterm emits device-status/attribute replies through onData too;
        # these are terminal protocol responses, not user typing.
        import re
        protocol_reply = bool(re.fullmatch(r"\x1b\[[?>]?[0-9;]*[RcnIO]", text))
        if protocol_reply:
            if self.pty:
                self.pty.write(text)
            return
        if self._restart_pending:
            self._restart_pending = False
            self.last_error = "Restart cancelled by keyboard input"
            self._deadline.stop()
        # Early typing cancels auto-start rather than interleaving commands.
        if self._startup_pending:
            self._startup_pending = False
            self.last_error = "Startup command cancelled by keyboard input"
        if "\r" in text:
            self.state = "running"
        if self.pty:
            self.pty.write(text)
        self.changed.emit()

    def _on_resize(self, cols, rows):
        if self.pty:
            self.pty.resize(cols, rows)

    def _on_exit(self):
        self.age.stop()
        self.exited.emit()

    def _mark_exited(self):
        self.state = "exited"
        self._startup_pending = self._restart_pending = False
        self._deadline.stop()
        self.changed.emit()

    def _timed_out(self):
        self._restart_pending = False
        self._startup_pending = False
        self.last_error = "Shell readiness timed out; command was not replayed"
        if self.state == "starting":
            self.state = "failed"
        self.changed.emit()

    def send_ctrl_c(self):
        if self.pty:
            self.pty.send_ctrl_c()

    def clear(self):
        if self.view:
            self.view.clear_terminal()

    def can_restart(self):
        return bool(self.restart_cmd) and self.state not in ("starting", "stopping", "exited", "failed") and not self._restart_pending

    def restart_reason(self):
        if not self.restart_cmd:
            return "Set an explicit restart command in the terminal/profile editor"
        if self._restart_pending:
            return "Waiting for shell prompt; keyboard input cancels replay"
        if self.shell == "cmd":
            return "CMD requires confirmation that the shell prompt is ready"
        return "" if self.can_restart() else f"Session {self.state}"

    def restart(self, confirmed=False):
        if not self.can_restart() or not self.pty:
            return
        if self.shell == "cmd" and not confirmed:
            self.last_error = "Send Ctrl+C, then confirm CMD prompt readiness before running"
            self.changed.emit()
            return
        command = self.restart_cmd
        if self.shell in ("pwsh", "powershell"):
            folder = self.cwd.replace("'", "''")
            if folder:
                command = f"Set-Location -LiteralPath '{folder}'; {command}"
        elif self.shell == "wsl" and self.cwd:
            command = f"cd -- {shlex.quote(self.cwd)} && {command}"
        elif self.shell == "cmd" and self.cwd:
            command = f'cd /d "{self.cwd}" && {command}'
        if self.shell == "cmd" or self.state == "ready":
            self._execute(command)
        else:
            self._restart_pending = True
            self._restart_command = command
            self.state = "stopping"
            self._deadline.start(10000)
            self.pty.send_ctrl_c()
        self.changed.emit()

    def descendant_infos(self):
        if self.pty:
            return self.pty.descendant_infos()
        return []

    def active_child_name(self):
        return self.child_name

    def close(self):
        self.age.stop()
        if self._closed.is_set():
            return
        self._closed.set()
        self._startup_pending = self._restart_pending = False
        if self.view and not getattr(self.view, "_closing", False):
            self.view.shutdown()
        if self._worker and self._worker is not threading.current_thread():
            self._worker.join(timeout=4)
        if self.wsl:
            # Explicit session close sends SIGHUP to verified Linux shell.
            # Never terminate a distro or use Windows forwarder PIDs.
            try:
                script = ('import os,signal,json; root=int(__import__("sys").argv[1]); '
                          'expected=int(__import__("sys").argv[2]); '
                          'stat=open("/proc/%d/stat"%root).read(); '
                          'assert int(stat.rsplit(")",1)[1].split()[19])==expected; '
                          'os.kill(root,signal.SIGHUP)')
                start = self.wsl.latest.get("procs", {}).get(str(self.wsl_shell_pid), {}).get("start", 0)
                if start:
                    args = ["-d", self.distro] if self.distro else []
                    subprocess.run(["wsl", *args, "--", "python3", "-c", script,
                                    str(self.wsl_shell_pid), str(start)], capture_output=True, timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
            self.wsl.close()
        if self.pty:
            self.pty.close()
        self.state = "exited"

    def to_saved(self):
        return SavedSession(name=self.name, shell=self.shell, cwd=self.current_cwd or self.cwd,
                            startup_cmd=self.startup_cmd, distro=self.distro,
                            id=self.definition_id, restart_cmd=self.restart_cmd,
                            workspace_profile_id=self.profile_id,
                            terminal_profile_id=self.definition_id,
                            instance_id=self.instance_id, accent=self.accent)


class SessionManager(QObject):
    sessionAdded = pyqtSignal(object)
    sessionRemoved = pyqtSignal(str)
    activeChanged = pyqtSignal(object)
    orderChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions = []
        self.active = None

    def create(self, shell, cwd="", name="", startup_cmd="", distro="",
               scrollback=10000, **metadata):
        session = TerminalSession(name or f"Terminal {len(self.sessions) + 1}", shell,
                                  cwd, startup_cmd, distro, scrollback, self)
        for key, value in metadata.items():
            setattr(session, key, value)
        self.sessions.append(session)
        self.sessionAdded.emit(session)
        self.set_active(session)
        return session

    def set_active(self, session):
        if session is not None and session not in self.sessions:
            return
        self.active = session
        self.activeChanged.emit(session)

    def launch_definition(self, profile, definition_id, instance_id=""):
        """Start one definition; command review belongs to the UI caller."""
        definition = next((d for d in profile.terminals if d.id == definition_id), None)
        if definition is None:
            raise ValueError("Terminal definition no longer belongs to workspace")
        existing_instance = next((s.instance_id for s in self.sessions
                                  if s.profile_id == profile.id), None)
        instance = instance_id or existing_instance or uuid.uuid4().hex
        existing = next((s for s in self.sessions if s.profile_id == profile.id
                         and s.instance_id == instance and s.definition_id == definition_id), None)
        if existing:
            self.set_active(existing)
            return existing
        return self.create(definition.shell, definition.cwd, definition.name,
                           definition.startup_cmd, definition.distro,
                           profile_id=profile.id, definition_id=definition.id,
                           instance_id=instance, restart_cmd=definition.restart_cmd or definition.startup_cmd,
                           accent=definition.accent, expected_ports=list(definition.expected_ports))

    def launch_profile(self, profile, duplicate=False, missing=False):
        existing = [s for s in self.sessions if s.profile_id == profile.id]
        if existing and not duplicate and not missing:
            self.set_active(existing[0])
            return existing
        instance = existing[0].instance_id if existing and missing else uuid.uuid4().hex
        present = {s.definition_id for s in existing if s.instance_id == instance}
        result = []
        for definition in profile.terminals:
            if missing and definition.id in present:
                continue
            session = self.create(definition.shell, definition.cwd, definition.name,
                                  definition.startup_cmd, definition.distro,
                                  profile_id=profile.id, definition_id=definition.id,
                                  instance_id=instance, restart_cmd=definition.restart_cmd or definition.startup_cmd,
                                  accent=definition.accent, expected_ports=list(definition.expected_ports))
            result.append(session)
        return result

    def close(self, session):
        if session in self.sessions:
            self.sessions.remove(session)
        self.sessionRemoved.emit(session.id)
        if self.active is session:
            self.set_active(self.sessions[-1] if self.sessions else None)

    def reorder(self, identifiers):
        mapping = {s.id: s for s in self.sessions}
        if len(identifiers) == len(mapping) and set(identifiers) == set(mapping):
            self.sessions[:] = [mapping[sid] for sid in identifiers]
            self.orderChanged.emit()

    def shutdown(self):
        for session in self.sessions:
            session.close()
        self.sessions.clear()
