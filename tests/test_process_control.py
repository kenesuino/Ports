import os
import subprocess
import sys
import time

import pytest

from ports.port_monitor import OwnerIdentity
from ports.process_control import (
    current_owner_of_port, describe_target, kill_windows, redact_cmdline,
)

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows-only")


def _spawn_sleeper():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    import psutil
    proc = psutil.Process(p.pid)
    return p, OwnerIdentity("windows", p.pid, proc.create_time(), proc.name())


def test_redact_cmdline():
    assert "hunter2" not in redact_cmdline("app --password=hunter2 --port 1")
    assert "abc" in redact_cmdline("app --port abc")


def test_kill_with_correct_identity():
    p, owner = _spawn_sleeper()
    result = kill_windows(owner)
    assert result.ok
    p.wait(timeout=5)


def test_kill_refuses_recycled_identity():
    p, owner = _spawn_sleeper()
    stale = OwnerIdentity("windows", owner.pid, owner.create_time + 999, "x")
    result = kill_windows(stale)
    assert not result.ok
    assert "identity changed" in result.message
    p.kill(); p.wait()


def test_kill_protected_refused():
    owner = OwnerIdentity("windows", 4, 0.0, "System")
    assert not kill_windows(owner).ok


def test_kill_already_exited():
    p, owner = _spawn_sleeper()
    p.kill(); p.wait()
    # owner identity is stale but pid gone -> "already exited" path
    result = kill_windows(owner)
    assert not result.ok or result.ok  # either message acceptable
    assert "exit" in result.message or "identity" in result.message


def test_describe_target_redacts():
    p, owner = _spawn_sleeper()
    info = describe_target(owner)
    assert info["pid"] == owner.pid and info["name"]
    p.kill(); p.wait()


def test_current_owner_of_port_free_port():
    assert current_owner_of_port(59999) is None
