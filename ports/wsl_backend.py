"""Windows-side coordinator for the WSL helper.

Spawns `wsl -d <distro> python3 -u <helper> <shell_pid>` with pipes and parses
JSON-line snapshots. Signals are sent as JSON commands on stdin.
"""

from __future__ import annotations

import json
import subprocess
import threading
import queue
import uuid
from dataclasses import dataclass

from . import wsl_helper


@dataclass
class WslListener:
    address: str
    port: int
    pid: int | None
    name: str
    start: int
    session_owned: bool


class WslBackend:
    """One per WSL terminal session. Not a Qt object; parent polls it."""

    def __init__(self, distro: str, shell_pid: int):
        self.distro = distro
        self.shell_pid = shell_pid
        self.latest: dict = {"listeners": [], "procs": {}}
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._closed = threading.Event()
        self.last_error = ""
        self._requests = {}
        self._write_lock = threading.Lock()

    def _args(self):
        return ["wsl", "-d", self.distro] if self.distro else ["wsl"]

    def available(self) -> tuple[bool, str]:
        """Check python3 + ss exist inside the distro without installing."""
        try:
            out = subprocess.run(
                [*self._args(), "--", "bash", "-lc",
                 "command -v python3 && command -v ss"],
                capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)
        if out.returncode != 0:
            return False, ("WSL distro needs python3 and iproute2 (ss). "
                           "Install with your distro's package manager.")
        return True, ""

    def start(self) -> bool:
        ok, msg = self.available()
        if not ok:
            self.last_error = msg
            return False
        src = wsl_helper.__file__
        # Convert Windows path to WSL path: F:\Github\... -> /mnt/f/Github/...
        drive = src[0].lower()
        wsl_path = "/mnt/" + drive + src[2:].replace("\\", "/")
        try:
            self._proc = subprocess.Popen(
                [*self._args(), "--", "python3", "-u",
                 wsl_path, str(self.shell_pid)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1)
        except OSError as e:
            self.last_error = str(e)
            return False
        threading.Thread(target=self._read_loop, daemon=True,
                         name=f"wsl-helper-{self.distro}").start()
        return True

    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            if self._closed.is_set():
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "snapshot":
                with self._lock:
                    self.latest = msg
            elif msg.get("type") == "ack":
                with self._lock:
                    target = self._requests.get(msg.get("id"))
                if target:
                    target.put(msg)

    def listeners(self) -> list[WslListener]:
        with self._lock:
            raw = list(self.latest.get("listeners", []))
        return [WslListener(
            address=l.get("address", ""), port=int(l.get("port", 0)),
            pid=l.get("pid"), name=l.get("name", ""),
            start=int(l.get("start", 0)),
            session_owned=bool(l.get("session_owned")))
            for l in raw]

    def send_signal(self, pid: int, sig: int, *, start=None, address=None, port=None):
        if not self._proc or not self._proc.stdin or self._closed.is_set():
            return {"ok": False, "message": "helper unavailable"}
        # Legacy callers may select a current snapshot owner; identity always
        # travels to the Linux helper for immediate validation.
        if start is None:
            selected = next((item for item in self.listeners() if item.pid == pid), None)
            if selected:
                start, address, port = selected.start, selected.address, selected.port
        request_id = uuid.uuid4().hex
        result_queue = queue.Queue(maxsize=1)
        with self._lock:
            self._requests[request_id] = result_queue
        try:
            with self._write_lock:
                self._proc.stdin.write(json.dumps({"cmd": "signal", "id": request_id,
                    "pid": pid, "sig": sig, "start": start, "address": address, "port": port}) + "\n")
                self._proc.stdin.flush()
            return result_queue.get(timeout=5)
        except (OSError, ValueError, queue.Empty) as exc:
            return {"ok": False, "message": f"Signal not acknowledged: {exc}"}
        finally:
            with self._lock:
                self._requests.pop(request_id, None)

    def close(self) -> None:
        self._closed.set()
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                try:
                    self._proc.kill()
                except OSError:
                    pass
