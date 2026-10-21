"""Session lifecycle: spawn, rename, close, restore, safe restart.

Restart contract: a session may only be restarted when it has an explicit
restart command (the startup command doubles as one). Restart sends Ctrl+C,
waits for descendants to exit (bounded), then writes the recorded command.
Blind history replay (Up+Enter) is never used.

WSL sessions wrap their shell so its Linux PID lands in a pidfile; the
WslBackend helper uses that PID for descendant/socket attribution.
"""

from __future__ import annotations

import itertools
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from .config_store import SavedSession
from .pty_session import PtySession, available_shells
from .terminal_view import TerminalView
from .wsl_backend import WslBackend

RESTART_WAIT_S = 6.0


class TerminalSession(QObject):
    changed = pyqtSignal()
    exited = pyqtSignal()
    view_factory = None  # defaults to TerminalView; tests may inject a stub

    def __init__(self, name: str, shell: str, cwd: str, startup_cmd: str = "",
                 distro: str = "", scrollback: int = 10000, parent=None):
        super().__init__(parent)
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.shell = shell
        self.cwd = cwd
        self.startup_cmd = startup_cmd
        self.distro = distro
        self.restart_cmd = startup_cmd  # explicit restart definition
        self.pty: PtySession | None = None
        self.view: TerminalView | None = None
        self.wsl: WslBackend | None = None
        self.wsl_shell_pid: int | None = None
        self.last_error = ""
        self._restarting = threading.Event()
        self._pidfile = ""

    # -- lifecycle ------------------------------------------------------

    def start(self, scrollback: int = 10000) -> None:
        factory = self.view_factory or TerminalView
        self.view = factory(scrollback=scrollback)
        self.view.inputReceived.connect(self._on_input)
        self.view.resizeReceived.connect(self._on_resize)

        shell = self.shell
        if shell == "wsl":
            self._pidfile = f"/tmp/ports-{self.id}.pid"
            # The pidfile wrapper lets the helper find the exact session shell.
            self.pty = PtySession(
                "wsl", on_data=self._on_pty_data, on_exit=self._on_exit,
                distro=self.distro)
            # override spawn cmdline through distro trick below
            self.pty._wsl_wrap = self._pidfile  # consumed by start()
        else:
            self.pty = PtySession(shell, cwd=self.cwd,
                                  on_data=self._on_pty_data,
                                  on_exit=self._on_exit)
        self.pty.start()

        if shell == "wsl":
            self._start_wsl_backend()

        if self.startup_cmd:
            # wait for shell readiness: bounded delay, not output parsing
            threading.Timer(0.6, self._send_startup).start()

    def _start_wsl_backend(self) -> None:
        def worker():
            deadline = time.time() + 15
            pid = None
            while time.time() < deadline and not pid:
                try:
                    out = subprocess.run(
                        ["wsl", "-d", self.distro, "--", "cat", self._pidfile],
                        capture_output=True, text=True, timeout=10)
                    text = out.stdout.strip()
                    if out.returncode == 0 and text.isdigit():
                        pid = int(text)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                if not pid:
                    time.sleep(0.5)
            if not pid:
                self.last_error = "could not identify WSL shell PID"
                self.changed.emit()
                return
            self.wsl_shell_pid = pid
            backend = WslBackend(self.distro or "Ubuntu", pid)
            if backend.start():
                self.wsl = backend
            else:
                self.last_error = backend.last_error
            self.changed.emit()
        threading.Thread(target=worker, daemon=True,
                         name=f"wsl-pid-{self.id}").start()

    def _send_startup(self) -> None:
        if self.pty and self.pty.isalive() and self.startup_cmd:
            self.pty.write(self.startup_cmd + "\r")

    def close(self) -> None:
        if self.wsl:
            self.wsl.close()
        if self.pty:
            self.pty.close()
        if self.view:
            self.view.shutdown()
        if self._pidfile and self.distro:
            try:
                subprocess.run(["wsl", "-d", self.distro, "--", "rm", "-f",
                                self._pidfile], capture_output=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass

    # -- I/O ------------------------------------------------------------

    def _on_input(self, text: str) -> None:
        if self.pty:
            self.pty.write(text)

    def _on_resize(self, cols: int, rows: int) -> None:
        if self.pty:
            self.pty.resize(cols, rows)

    def _on_pty_data(self, data: bytes) -> None:
        if self.view:
            self.view.feed(data)

    def _on_exit(self) -> None:
        self.exited.emit()

    # -- actions --------------------------------------------------------

    def send_ctrl_c(self) -> None:
        if self.pty:
            self.pty.send_ctrl_c()

    def clear(self) -> None:
        if self.view:
            self.view.clear_terminal()

    def can_restart(self) -> bool:
        return bool(self.restart_cmd) and not self._restarting.is_set()

    def restart_reason(self) -> str:
        if self._restarting.is_set():
            return "restart in progress"
        if not self.restart_cmd:
            return ("no restart command recorded; set a startup command when "
                    "creating the session")
        return ""

    def restart(self) -> None:
        """Ctrl+C, wait for descendants to exit, re-run recorded command."""
        if not self.can_restart() or not self.pty:
            return
        self._restarting.set()
        self.changed.emit()

        def worker():
            try:
                self.pty.send_ctrl_c()
                deadline = time.time() + RESTART_WAIT_S
                while time.time() < deadline:
                    if not self.pty.isalive():
                        return  # shell died; do not type into the void
                    if not self.pty.descendant_pids():
                        break
                    time.sleep(0.2)
                else:
                    return  # timeout: cancel replay, leave shell as-is
                time.sleep(0.3)  # let the prompt settle
                if self.pty.isalive():
                    self.pty.write(self.restart_cmd + "\r")
            finally:
                self._restarting.clear()
                self.changed.emit()

        threading.Thread(target=worker, daemon=True,
                         name=f"restart-{self.id}").start()

    # -- introspection --------------------------------------------------

    def descendant_infos(self) -> list[dict]:
        if self.pty:
            return self.pty.descendant_infos()
        return []

    def active_child_name(self) -> str:
        infos = self.descendant_infos()
        if not infos:
            return ""
        # deepest / most recent child is the interesting one
        infos.sort(key=lambda i: i["create_time"])
        return infos[-1]["name"]

    def to_saved(self) -> SavedSession:
        return SavedSession(self.name, self.shell, self.cwd,
                            self.startup_cmd, self.distro)


class SessionManager(QObject):
    sessionAdded = pyqtSignal(object)
    sessionRemoved = pyqtSignal(str)
    activeChanged = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions: list[TerminalSession] = []
        self.active: TerminalSession | None = None
        self._counter = itertools.count(1)

    def create(self, shell: str, cwd: str = "", name: str = "",
               startup_cmd: str = "", distro: str = "",
               scrollback: int = 10000) -> TerminalSession:
        if not name:
            name = f"Terminal {next(self._counter)}"
        s = TerminalSession(name, shell, cwd, startup_cmd, distro,
                            scrollback, parent=self)
        self.sessions.append(s)
        s.exited.connect(lambda s=s: self._on_exited(s))
        self.sessionAdded.emit(s)
        self.set_active(s)
        return s

    def set_active(self, session: TerminalSession) -> None:
        self.active = session
        self.activeChanged.emit(session)

    def close(self, session: TerminalSession) -> None:
        if session in self.sessions:
            self.sessions.remove(session)
        session.close()
        self.sessionRemoved.emit(session.id)
        if self.active is session:
            self.active = self.sessions[-1] if self.sessions else None
            self.activeChanged.emit(self.active)

    def _on_exited(self, session: TerminalSession) -> None:
        session.changed.emit()

    def shutdown(self) -> None:
        for s in list(self.sessions):
            s.close()
        self.sessions.clear()
