import pytest

from ports.port_monitor import (
    Listener, OwnerIdentity, filter_noise, is_localhost, map_ports,
    merge_wsl_forwarders,
)


def lst(port, pid, name="python.exe", addr="127.0.0.1", ct=100.0):
    owner = OwnerIdentity("windows", pid, ct, name) if pid else None
    return Listener(addr, port, owner)


def test_localhost_detection():
    for a in ("127.0.0.1", "::1", "0.0.0.0", "::", "127.0.0.55"):
        assert is_localhost(a)
    for a in ("192.168.1.5", "10.0.0.2", "8.8.8.8"):
        assert not is_localhost(a)


def test_map_ports_to_session_members():
    sessions = {"s1": {100, 101}, "s2": {200}}
    listeners = [lst(3000, 101), lst(5173, 200), lst(8080, 999)]
    attributed, rest = map_ports(sessions, listeners)
    assert [l.port for l in attributed["s1"]] == [3000]
    assert [l.port for l in attributed["s2"]] == [5173]
    assert [l.port for l in rest] == [8080]


def test_map_ports_unknown_owner_goes_external():
    attributed, rest = map_ports({"s1": {1}}, [lst(80, None)])
    assert attributed["s1"] == []
    assert len(rest) == 1


def test_filter_noise_deny_and_allow():
    deny, allow = ["svchost.exe"], []
    assert not filter_noise(lst(135, 4, "svchost.exe"), deny, allow)
    assert filter_noise(lst(3000, 5, "node.exe"), deny, allow)
    assert filter_noise(lst(135, 4, "svchost.exe"), deny, ["svchost.exe"])


def test_filter_noise_unknown_owner_kept():
    assert filter_noise(lst(9000, None), ["svchost.exe"], [])


def test_merge_wsl_forwarders_drops_duplicates():
    win = [lst(3000, 50, "wslrelay.exe"), lst(4000, 51, "node.exe")]
    wsl = {"s1": [Listener("0.0.0.0", 3000, None, env="wsl", distro="Ubuntu")]}
    out = merge_wsl_forwarders(win, wsl)
    assert [l.port for l in out] == [4000]


def test_merge_wsl_forwarders_keeps_non_forwarded():
    win = [lst(5000, 50, "wslrelay.exe")]
    out = merge_wsl_forwarders(win, {})
    assert len(out) == 1


def test_protected_never_external():
    assert not filter_noise(lst(445, 4, "System"), [], [])
