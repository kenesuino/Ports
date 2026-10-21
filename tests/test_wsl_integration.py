"""WSL end-to-end: session shell PID discovery, port attribution, signal.

Requires an installed Ubuntu distro with python3. Skipped otherwise.
"""

import os
import subprocess
import time

import pytest

from ports.pty_session import PtySession
from ports.wsl_backend import WslBackend

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows-only")

PORT = 54872
DISTRO = "Ubuntu"


def _wsl_ready():
    try:
        out = subprocess.run(
            ["wsl", "-d", DISTRO, "--", "bash", "-lc",
             "command -v python3 >/dev/null && echo ok"],
            capture_output=True, text=True, timeout=30)
        return out.returncode == 0 and "ok" in out.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def _wait(fn, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.5)
    return False


def test_wsl_attribution_and_signal():
    if not _wsl_ready():
        pytest.skip("Ubuntu distro with python3 not available")

    pidfile = f"/tmp/ports-test-{os.getpid()}.pid"
    pty = PtySession("wsl", distro=DISTRO)
    pty._wsl_wrap = pidfile
    pty.start()
    backend = None
    try:
        # wait for the pidfile written by the bash wrapper
        shell_pid = None

        def read_pid():
            nonlocal shell_pid
            try:
                out = subprocess.run(
                    ["wsl", "-d", DISTRO, "--", "cat", pidfile],
                    capture_output=True, text=True, timeout=10)
                if out.returncode == 0 and out.stdout.strip().isdigit():
                    shell_pid = int(out.stdout.strip())
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
            return False

        assert _wait(read_pid), "pidfile never appeared"
        backend = WslBackend(DISTRO, shell_pid)
        assert backend.start(), backend.last_error

        # start a server inside the session terminal
        pty.write(f"python3 -m http.server {PORT} &\r")

        def has_port():
            return any(l.port == PORT and l.session_owned
                       for l in backend.listeners())

        assert _wait(has_port), "WSL listener not attributed to session"

        # signal it away through the helper
        pid = next(l.pid for l in backend.listeners()
                   if l.port == PORT and l.session_owned)
        backend.send_signal(pid, 15)

        def gone():
            return not any(l.port == PORT for l in backend.listeners())

        assert _wait(gone), "listener survived SIGTERM"
        assert pty.isalive(), "WSL shell died"
    finally:
        if backend:
            backend.close()
        pty.close()
        subprocess.run(["wsl", "-d", DISTRO, "--", "rm", "-f", pidfile],
                       capture_output=True, timeout=10)
