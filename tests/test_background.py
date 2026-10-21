"""Verify snapshot failures remain errors, not empty successful snapshots."""
import pytest
from ports import port_monitor
from ports.background import collect_snapshot


def test_monitor_error_propagates(monkeypatch):
    def denied(**kwargs):
        raise port_monitor.psutil.AccessDenied()
    monkeypatch.setattr(port_monitor.psutil, "net_connections", denied)
    with pytest.raises(port_monitor.psutil.AccessDenied):
        collect_snapshot(())


def test_no_sessions_collects_external(monkeypatch):
    listener = port_monitor.Listener("127.0.0.1", 23456, None)
    monkeypatch.setattr("ports.background.collect_windows_listeners", lambda: [listener])
    attributed, external, children, errors = collect_snapshot(())
    assert attributed == {}
    assert external == [listener]
    assert children == {}
    assert errors == []
