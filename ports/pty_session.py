"""ConPTY session wrapper with Job Object descendant tracking.

Each session spawns a shell through pywinpty (ConPTY backend) and assigns the
shell process to a Windows Job Object. Job membership lets us enumerate all
descendants - including grandchildren whose intermediate parent exited - which
plain process-tree polling misses.

Threading: a daemon reader thread pulls bytes from the PTY and invokes the
`on_data` callback. All writes are serialized through a lock.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import threading
import time
from ctypes import wintypes

import psutil
from winpty import PTY

# ---------------------------------------------------------------- Job Object

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

JobObjectBasicProcessIdList = 3
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_INFORMATION = 0x0400


class _JobBasicProcessIdList(ctypes.Structure):
    _fields_ = [
        ("NumberOfAssignedProcesses", wintypes.DWORD),
        ("NumberOfProcessIdsInList", wintypes.DWORD),
        ("ProcessIdList", ctypes.c_size_t * 1),
    ]


class JobTracker:
    """Assigns one process to a Job Object and enumerates its members."""

    def __init__(self, pid: int):
        self._job = kernel32.CreateJobObjectW(None, None)
        if not self._job:
            raise ctypes.WinError(ctypes.get_last_error())
        handle = kernel32.OpenProcess(
            PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_QUERY_INFORMATION,
            False, pid)
        if not handle:
            kernel32.CloseHandle(self._job)
            self._job = None
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel32.AssignProcessToJobObject(self._job, handle):
                err = ctypes.get_last_error()
                kernel32.CloseHandle(self._job)
                self._job = None
                raise ctypes.WinError(err)
        finally:
            kernel32.CloseHandle(handle)

    def pids(self) -> set[int]:
        """Current job member PIDs (live + exited-but-tracked may vanish)."""
        if not self._job:
            return set()
        size = 64 + 8 * 256
        for _ in range(4):
            buf = ctypes.create_string_buffer(size)
            needed = wintypes.DWORD(0)
            ok = kernel32.QueryInformationJobObject(
                self._job, JobObjectBasicProcessIdList,
                buf, size, ctypes.byref(needed))
            if ok:
                count = wintypes.DWORD.from_buffer(buf, 4).value
                arr = (ctypes.c_size_t * count).from_buffer(buf, 8)
                return {int(p) for p in arr}
            size = 64 + 8 * (needed.value // 8 + 64)
        return set()

    def close(self) -> None:
        if self._job:
            kernel32.CloseHandle(self._job)
            self._job = None


# ------------------------------------------------------------------- Shells

SHELLS = {
    "pwsh": {"exe": "pwsh.exe", "label": "PowerShell 7"},
    "powershell": {"exe": "powershell.exe", "label": "Windows PowerShell"},
    "cmd": {"exe": "cmd.exe", "label": "CMD"},
    "wsl": {"exe": "wsl.exe", "label": "WSL"},
}


def available_shells() -> dict[str, str]:
    """shell key -> absolute exe path, for shells present on this machine."""
    found = {}
    for key, spec in SHELLS.items():
        path = shutil.which(spec["exe"])
        if path:
            found[key] = path
    return found


class PtySession:
    """One interactive ConPTY terminal session."""

    def __init__(self, shell: str, cwd: str = "", cols: int = 120, rows: int = 30,
                 on_data=None, on_exit=None, distro: str = ""):
        self.shell = shell
        self.distro = distro
        self.cwd = cwd or os.path.expanduser("~")
        self.on_data = on_data      # callable(bytes)
        self.on_exit = on_exit      # callable()
        self.cols, self.rows = cols, rows
        self.pid: int | None = None
        self.create_time: float | None = None
        self.job: JobTracker | None = None
        self._write_lock = threading.Lock()
        self._closed = threading.Event()
        self._pty = PTY(cols, rows)
        self._reader: threading.Thread | None = None

    # -- lifecycle ------------------------------------------------------

    def start(self) -> None:
        exe = SHELLS[self.shell]["exe"]
        cmdline = None
        if self.shell == "wsl":
            args = []
            if self.distro:
                args += ["-d", self.distro]
            wrap = getattr(self, "_wsl_wrap", "")
            if wrap:
                # record the Linux shell PID for the helper, then exec a login
                # shell so the session behaves like a normal WSL terminal
                args += ["--", "bash", "--noprofile", "--norc", "-c",
                         f"echo $$ > {wrap}; exec bash -l"]
            cmdline = subprocess.list2cmdline(args) if args else None
            self.cwd = ""  # WSL starts in its own home
        self._pty.spawn(exe, cmdline=cmdline, cwd=self.cwd or None)
        self.pid = self._pty.pid
        try:
            self.create_time = psutil.Process(self.pid).create_time()
        except (psutil.Error, OSError):
            self.create_time = time.time()
        if self.shell != "wsl":
            # WSL guest processes are invisible to the Windows job object.
            try:
                self.job = JobTracker(self.pid)
            except OSError:
                self.job = None  # fall back to psutil tree polling
        self._reader = threading.Thread(target=self._read_loop, daemon=True,
                                        name=f"pty-reader-{self.pid}")
        self._reader.start()

    def _read_loop(self) -> None:
        while not self._closed.is_set():
            try:
                data = self._pty.read(blocking=True)
            except (EOFError, OSError):
                break
            if not data:
                break
            if self.on_data:
                try:
                    self.on_data(data.encode("utf-8", "replace")
                                 if isinstance(data, str) else data)
                except Exception:
                    pass  # a dead UI must not kill the reader
        if self.on_exit:
            self.on_exit()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._pty.cancel_io()
        except Exception:
            pass
        if self.job:
            self.job.close()
        # Kill the shell tree so servers don't linger after tab close.
        if self.pid:
            try:
                parent = psutil.Process(self.pid)
                for child in parent.children(recursive=True):
                    try:
                        child.kill()
                    except psutil.Error:
                        pass
                parent.kill()
                try:
                    parent.wait(timeout=3)
                except psutil.TimeoutExpired:
                    pass
            except psutil.Error:
                pass

    # -- I/O ------------------------------------------------------------

    def write(self, text: str) -> None:
        with self._write_lock:
            if not self._closed.is_set():
                try:
                    self._pty.write(text)
                except OSError:
                    pass

    def send_ctrl_c(self) -> None:
        self.write("\x03")

    def resize(self, cols: int, rows: int) -> None:
        cols, rows = max(2, cols), max(2, rows)
        self.cols, self.rows = cols, rows
        try:
            self._pty.set_size(cols, rows)
        except OSError:
            pass

    def isalive(self) -> bool:
        try:
            return self._pty.isalive()
        except OSError:
            return False

    # -- descendants ----------------------------------------------------

    def descendant_pids(self) -> set[int]:
        """Live descendant PIDs: Job Object first, psutil tree as fallback."""
        if self.job:
            job_pids = self.job.pids() - {self.pid}
            live = {p for p in job_pids if psutil.pid_exists(p)}
            if live:
                return live
        if self.pid and psutil.pid_exists(self.pid):
            try:
                return {c.pid for c in
                        psutil.Process(self.pid).children(recursive=True)}
            except psutil.Error:
                pass
        return set()

    def descendant_infos(self) -> list[dict]:
        """pid/name/cmdline/create_time for live descendants."""
        out = []
        for pid in self.descendant_pids():
            try:
                p = psutil.Process(pid)
                out.append({
                    "pid": pid,
                    "name": p.name(),
                    "cmdline": p.cmdline(),
                    "create_time": p.create_time(),
                })
            except psutil.Error:
                continue
        return out
