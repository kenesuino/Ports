"""ConPTY bootstrap: wait for job assignment before executing user shell."""
import ctypes
from ctypes import wintypes
import subprocess
import sys

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel.OpenEventW.restype = wintypes.HANDLE
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
handle = kernel.OpenEventW(0x00100000, False, sys.argv[1])
if not handle:
    raise SystemExit(2)
result = kernel.WaitForSingleObject(handle, 30000)
kernel.CloseHandle(handle)
if result:
    raise SystemExit(3)
raise SystemExit(subprocess.call(sys.argv[2:]))
