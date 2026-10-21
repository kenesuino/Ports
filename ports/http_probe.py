"""Optional HTTP response checks for listeners.

States: responding (with status code), timeout, refused, protocol_mismatch,
unchecked. Never claims healthy/unhealthy. No redirects, no proxy, loopback
only.
"""

from __future__ import annotations

import socket
import ssl
import threading
from dataclasses import dataclass

MAX_WORKERS = 4
TIMEOUT = 1.0


@dataclass
class ProbeResult:
    state: str          # responding | timeout | refused | protocol_mismatch
    status: int = 0     # HTTP status when responding
    detail: str = ""

    @property
    def label(self) -> str:
        if self.state == "responding":
            return f"HTTP {self.status}"
        return {"timeout": "timeout", "refused": "refused",
                "protocol_mismatch": "not HTTP"}.get(self.state, self.state)


def probe(port: int, host: str = "127.0.0.1", use_https: bool = False,
          timeout: float = TIMEOUT) -> ProbeResult:
    if not (1 <= port <= 65535):
        return ProbeResult("refused", detail="invalid port")
    # Connect WITHOUT a timeout first: on Windows, create_connection with a
    # timeout reports refused loopback connections as bare TimeoutError.
    # Loopback refusal is instant, so a blocking connect is safe here.
    try:
        sock = socket.create_connection((host, port))
    except ConnectionRefusedError:
        return ProbeResult("refused")
    except (TimeoutError, socket.timeout):
        return ProbeResult("timeout")
    except OSError as e:
        if getattr(e, "errno", None) in (10061, 111, 61, 10054, 104):
            return ProbeResult("refused")
        return ProbeResult("protocol_mismatch", detail=str(e)[:80])
    try:
        sock.settimeout(timeout)
        if use_https:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
        sock.sendall(b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n")
        data = sock.recv(256)
        if not data:
            return ProbeResult("protocol_mismatch", detail="empty reply")
        first = data.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = first.split()
        if len(parts) >= 2 and parts[0].startswith("HTTP/") \
                and parts[1].isdigit():
            return ProbeResult("responding", status=int(parts[1]))
        return ProbeResult("protocol_mismatch", detail=first[:60])
    except ssl.SSLError:
        return ProbeResult("protocol_mismatch", detail="TLS mismatch")
    except (TimeoutError, socket.timeout):
        return ProbeResult("timeout")
    except (ConnectionResetError, BrokenPipeError):
        return ProbeResult("protocol_mismatch", detail="connection reset")
    except OSError as e:
        return ProbeResult("protocol_mismatch", detail=str(e)[:80])
    finally:
        try:
            sock.close()
        except OSError:
            pass


class ProbePool:
    """Bounded background probe runner; results delivered via callback."""

    def __init__(self, on_result):
        self.on_result = on_result  # callable(key, ProbeResult)
        self._sem = threading.Semaphore(MAX_WORKERS)
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._closed = False

    def request(self, key: str, port: int, use_https: bool = False) -> None:
        with self._lock:
            if self._closed or key in self._pending:
                return
            self._pending.add(key)
        threading.Thread(target=self._run,
                         args=(key, port, use_https), daemon=True).start()

    def _run(self, key: str, port: int, use_https: bool) -> None:
        with self._sem:
            result = probe(port, use_https=use_https)
        with self._lock:
            self._pending.discard(key)
            closed = self._closed
        if not closed:
            try:
                self.on_result(key, result)
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            self._closed = True
