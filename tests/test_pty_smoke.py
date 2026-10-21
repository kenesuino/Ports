import os
import sys
import time

import pytest

from ports.pty_session import PtySession, available_shells

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows-only")


def _spawn(shell, cwd=""):
    data = bytearray()
    s = PtySession(shell, cwd=cwd, on_data=lambda b: data.extend(b))
    s.start()
    return s, data


def _wait_for(data, marker: bytes, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if marker in bytes(data):
            return True
        time.sleep(0.1)
    return False


def test_cmd_echo_roundtrip():
    shells = available_shells()
    if "cmd" not in shells:
        pytest.skip("cmd.exe not found")
    s, data = _spawn("cmd")
    try:
        assert s.pid and s.pid > 0
        s.write("echo PORTS_MARKER_42\r")
        assert _wait_for(data, b"PORTS_MARKER_42")
    finally:
        s.close()
    assert not s.isalive()


def test_ctrl_c_and_descendants():
    shells = available_shells()
    if "cmd" not in shells:
        pytest.skip("cmd.exe not found")
    s, data = _spawn("cmd")
    try:
        s.write("ping -t 127.0.0.1\r")
        assert _wait_for(data, b"Pinging")
        time.sleep(0.5)
        kids = s.descendant_pids()
        assert kids, "job object should report ping.exe"
        s.send_ctrl_c()
        end = time.time() + 15
        while time.time() < end and s.descendant_pids():
            time.sleep(0.2)
        assert not s.descendant_pids(), "ping should be gone after Ctrl+C"
    finally:
        s.close()


def test_resize_and_alive():
    shells = available_shells()
    if "cmd" not in shells:
        pytest.skip("cmd.exe not found")
    s, _ = _spawn("cmd")
    try:
        s.resize(200, 50)
        assert s.cols == 200 and s.rows == 50
        assert s.isalive()
    finally:
        s.close()
