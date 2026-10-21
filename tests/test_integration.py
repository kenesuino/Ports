"""End-to-end: spawn session, start a server in it, attribute the port,
kill the port owner, verify the shell survives. Offscreen Qt."""

import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows-only")

PORT = 54871


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication.instance() or QApplication([])
    yield app


def _wait(fn, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.25)
    return False


def test_full_cycle(qapp):
    from PyQt6.QtCore import QObject, pyqtSignal

    from ports.port_monitor import collect_windows_listeners, map_ports
    from ports.process_control import current_owner_of_port, kill_windows
    from ports.session_manager import SessionManager, TerminalSession

    class StubView(QObject):
        """Headless TerminalView stand-in (WebEngine crashes offscreen)."""
        inputReceived = pyqtSignal(str)
        resizeReceived = pyqtSignal(int, int)

        def __init__(self, scrollback=0):
            super().__init__()
            self.buffer = bytearray()

        def feed(self, data): self.buffer.extend(data)
        def shutdown(self): pass
        def clear_terminal(self): pass
        def refit(self): pass
        def focus_terminal(self): pass
        def search(self, needle, backwards=False): pass

    TerminalSession.view_factory = StubView
    try:
        mgr = SessionManager()
        s = mgr.create("cmd", name="itest")
        s.start()
        try:
            assert _wait(lambda: s.pty and s.pty.isalive())
            # start an HTTP server inside the session
            s.pty.write(
                f'start "" /min "{sys.executable}" -m http.server {PORT}\r')
            assert _wait(lambda: current_owner_of_port(PORT) is not None)

            listeners = collect_windows_listeners()
            members = {s.id: s.pty.descendant_pids()}
            attributed, _ = map_ports(members, listeners)
            ports = [l.port for l in attributed.get(s.id, [])]
            assert PORT in ports, f"port not attributed; members={members}"

            # kill the port owner; shell must survive
            owner = current_owner_of_port(PORT)
            result = kill_windows(owner)
            assert result.ok, result.message
            assert _wait(lambda: current_owner_of_port(PORT) is None)
            time.sleep(0.5)
            assert s.pty.isalive(), "parent shell died"

            # shell still interactive: typed input flows back out
            s.pty.write("echo STILL_ALIVE\r")
            assert _wait(lambda: b"STILL_ALIVE" in bytes(s.view.buffer))
        finally:
            s.close()
            mgr.shutdown()
    finally:
        TerminalSession.view_factory = None
    assert not s.pty.isalive()
