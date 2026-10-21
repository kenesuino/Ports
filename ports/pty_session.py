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
import sys
import uuid
from pathlib import Path
from ctypes import wintypes

import psutil
from winpty import PTY

# ---------------------------------------------------------------- Job Object

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
kernel32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryInformationJobObject.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.SetEvent.restype = wintypes.BOOL

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


def windows_process_name(pid):
    try:
        return psutil.Process(pid).name().lower()
    except psutil.Error:
        return ""


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
        self._shell_pid = None
        self.launch_args = []
        self.attribution_error = ""

    # -- lifecycle ------------------------------------------------------

    def start(self) -> None:
        exe = SHELLS[self.shell]["exe"]
        cmdline = subprocess.list2cmdline(self.launch_args) if self.launch_args else None
        if self.shell == "wsl":
            args = []
            if self.distro:
                args += ["-d", self.distro]
            wrap = getattr(self, "_wsl_wrap", "")
            custom = getattr(self, "_wsl_command", None)
            if custom:
                args += ["--", *custom]
            elif wrap:
                # record the Linux shell PID for the helper, then exec a login
                # shell so the session behaves like a normal WSL terminal
                args += ["--", "bash", "--noprofile", "--norc", "-c",
                         f"echo $$ > {wrap}; exec bash -l"]
            cmdline = subprocess.list2cmdline(args) if args else None
            self.cwd = ""  # WSL starts in its own home
        barrier = None
        if self.shell != "wsl":
            name = "Local\\Ports-" + uuid.uuid4().hex
            barrier = kernel32.CreateEventW(None, True, False, name)
            if not barrier:
                raise ctypes.WinError(ctypes.get_last_error())
            bootstrap = str(Path(__file__).parent / "shell_integration" / "bootstrap.py")
            target = shutil.which(exe) or exe
            arguments = [bootstrap, name, target, *self.launch_args]
            exe = sys.executable
            cmdline = subprocess.list2cmdline(arguments)
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
            except OSError as exc:
                self.job = None
                self.attribution_error = f"Job tracking unavailable; ancestry fallback: {exc}"
        if barrier:
            self._barrier_handle = barrier
            kernel32.SetEvent(barrier)
        self._reader = threading.Thread(target=self._read_loop, daemon=True,
                                        name=f"pty-reader-{self.pid}")
        self._reader.start()

    def _read_loop(self) -> None:
        while not self._closed.is_set():
            try:
                data = self._pty.read(blocking=True)
            except Exception as exc:
                if not self._closed.is_set():
                    self.attribution_error = f"PTY reader stopped: {exc}"
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
        barrier = getattr(self, "_barrier_handle", None)
        if barrier:
            kernel32.CloseHandle(barrier)
            self._barrier_handle = None
        try:
            self._pty.cancel_io()
        except Exception:
            pass
        # Capture job members before releasing tracking: orphaned grandchildren
        # are no longer reachable through Process.children().
        members = self.descendant_infos()
        for item in members:
            try:
                child = psutil.Process(item["pid"])
                if child.create_time() == item["create_time"]:
                    child.kill()
            except psutil.Error:
                pass
        if self._shell_pid:
            try:
                shell = psutil.Process(self._shell_pid)
                if shell.ppid() == self.pid:
                    shell.kill()
            except psutil.Error:
                pass
        if self.pid:
            try:
                for process in psutil.Process(self.pid).children(recursive=True):
                    if process.pid not in {item['pid'] for item in members}:
                        try:
                            process.kill()
                        except psutil.Error:
                            pass
            except psutil.Error:
                pass
        if self.job:
            self.job.close()
        if self.pid:
            try:
                parent = psutil.Process(self.pid)
                if parent.create_time() != self.create_time:
                    return
                parent.kill()
                try:
                    parent.wait(timeout=3)
                except psutil.TimeoutExpired:
                    pass
            except psutil.Error:
                pass
        if self._reader and self._reader is not threading.current_thread():
            self._reader.join(timeout=2)

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
            excluded = {self.pid}
            try:
                direct = psutil.Process(self.pid).children(recursive=True)
                self._shell_pid = next((p.pid for p in direct if p.name().lower() == SHELLS[self.shell]["exe"].lower()), self._shell_pid)
                for process in direct:
                    try:
                        if any(arg.endswith("bootstrap.py") for arg in process.cmdline()):
                            excluded.add(process.pid)
                    except psutil.Error:
                        pass
                if self._shell_pid:
                    excluded.add(self._shell_pid)
            except psutil.Error:
                pass
            job_pids = self.job.pids() - excluded
            live = {p for p in job_pids if psutil.pid_exists(p) and windows_process_name(p) != "conhost.exe"}
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
