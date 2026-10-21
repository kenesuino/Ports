import ctypes
from ctypes import wintypes
from unittest.mock import Mock

from ports import wsl_helper
from ports.port_monitor import OwnerIdentity
from ports.process_control import _identity_matches


def test_reused_pid_less_than_one_second_is_rejected():
    process = Mock(pid=12)
    process.create_time.return_value = 100.25
    assert not _identity_matches(process, OwnerIdentity("windows", 12, 100.0))


def test_invalid_wsl_pid_never_signals(monkeypatch):
    kill = Mock()
    monkeypatch.setattr(wsl_helper.os, "kill", kill)
    for pid in (0, -1, 1):
        result = wsl_helper.handle_command({"cmd": "signal", "pid": pid, "sig": 15})
        assert not result["ok"]
    kill.assert_not_called()


def test_missing_wsl_identity_rejected(monkeypatch):
    kill = Mock()
    monkeypatch.setattr(wsl_helper.os, "kill", kill)
    assert not wsl_helper.handle_command({"cmd": "signal", "pid": 54321, "sig": 15})["ok"]
    kill.assert_not_called()
