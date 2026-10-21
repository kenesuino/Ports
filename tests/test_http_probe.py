import socket
import subprocess
import sys
import time

import pytest

from ports.http_probe import ProbePool, probe


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_probe_responding():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port),
                            "--bind", "127.0.0.1"])
    try:
        time.sleep(1.0)
        result = probe(port)
        assert result.state == "responding"
        assert result.status in (200, 404)
        assert "HTTP" in result.label
    finally:
        srv.kill()
        srv.wait()


def test_probe_refused():
    port = _free_port()
    assert probe(port).state in ("refused", "timeout")


def test_probe_invalid_port():
    assert probe(0).state == "refused"


def test_probe_pool_bounds_and_callback():
    port = _free_port()
    results = []
    pool = ProbePool(lambda k, r: results.append((k, r)))
    try:
        for i in range(8):
            pool.request(f"k{i}", port)
        end = time.time() + 10
        while time.time() < end and len(results) < 8:
            time.sleep(0.1)
        assert len(results) == 8
        assert all(r.state in ("refused", "timeout") for _, r in results)
    finally:
        pool.close()
