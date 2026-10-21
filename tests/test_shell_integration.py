"""Shell hooks with real ConPTY and an event-pumping Qt application."""
import os
import time
import pytest
from PyQt6.QtCore import QCoreApplication

from ports.session_manager import TerminalSession
from ports.pty_session import available_shells


class FakeView:
    _closing = False
    def __init__(self): self.buffer = bytearray()
    def feed(self, data): self.buffer.extend(data)
    def shutdown(self): self._closing = True


def test_real_powershell_prompt_runs_startup_once():
    shell = "pwsh" if "pwsh" in available_shells() else "powershell"
    app = QCoreApplication.instance() or QCoreApplication([])
    session = TerminalSession("hook-check", shell, os.getcwd(), "Write-Output PORTS_HOOK_SUCCESS")
    session.view = FakeView()
    session._spawn_worker()
    try:
        end = time.monotonic() + 15
        while time.monotonic() < end:
            app.processEvents()
            if b"PORTS_HOOK_SUCCESS" in bytes(session.view.buffer) and session.current_cwd:
                break
            time.sleep(.05)
        assert session.current_cwd, session.last_error
        assert b"PORTS_HOOK_SUCCESS" in bytes(session.view.buffer)
        assert not session._startup_pending
    finally:
        session.close()
