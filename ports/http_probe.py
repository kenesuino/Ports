"""Optional bounded loopback HTTP response checks; no redirects or proxy use."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import ipaddress
import socket
import ssl
import threading
import time

MAX_WORKERS = 4
TIMEOUT = 1.0


@dataclass
class ProbeResult:
    state: str
    status: int = 0
    detail: str = ""
    @property
    def label(self):
        return f"HTTP {self.status}" if self.state == "responding" else {"protocol_mismatch": "not HTTP"}.get(self.state, self.state)


def probe(port, host="127.0.0.1", use_https=False, timeout=TIMEOUT):
    try:
        address = ipaddress.ip_address(host)
        if not address.is_loopback or type(port) is not int or not 1 <= port <= 65535:
            return ProbeResult("refused", detail="Invalid loopback endpoint")
    except ValueError:
        return ProbeResult("refused", detail="Numeric loopback address required")
    deadline = time.monotonic() + timeout
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(max(.001, deadline - time.monotonic()))
        if use_https:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        sock.settimeout(max(.001, deadline - time.monotonic()))
        sock.sendall(b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n")
        data = bytearray()
        while b"\r\n" not in data and len(data) < 1024:
            left = deadline - time.monotonic()
            if left <= 0:
                return ProbeResult("timeout")
            sock.settimeout(left)
            piece = sock.recv(256)
            if not piece:
                break
            data.extend(piece)
        parts = bytes(data).split(b"\r\n", 1)[0].split()
        if len(parts) >= 2 and parts[0].startswith(b"HTTP/") and parts[1].isdigit():
            return ProbeResult("responding", int(parts[1]))
        return ProbeResult("protocol_mismatch")
    except ConnectionRefusedError:
        return ProbeResult("refused")
    except TimeoutError:
        return ProbeResult("timeout")
    except (OSError, ssl.SSLError) as exc:
        return ProbeResult("protocol_mismatch", detail=str(exc)[:120])
    finally:
        if sock:
            sock.close()


class ProbePool:
    def __init__(self, on_result):
        self.on_result = on_result
        self.pool = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="http-probe")
        self._lock = threading.Lock()
        self._pending = set()
        self._closed = False

    def request(self, key, port, use_https=False, host="127.0.0.1"):
        with self._lock:
            if self._closed or key in self._pending or len(self._pending) >= 32:
                return False
            self._pending.add(key)
        future = self.pool.submit(probe, port, host, use_https)
        def done(result):
            with self._lock:
                self._pending.discard(key)
                closed = self._closed
            if not closed:
                try:
                    self.on_result(key, result.result())
                except Exception:
                    pass
        future.add_done_callback(done)
        return True

    def close(self):
        with self._lock:
            self._closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
