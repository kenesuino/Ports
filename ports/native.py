"""Windows shell integration: dark title bar and rounded corners.

Both calls are best-effort. Any unsupported attribute, older Windows build, or
non-Windows host is ignored so the app still launches.
"""

from __future__ import annotations

import ctypes
import os
import sys

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


def _set_attribute(hwnd: int, attribute: int, value: int) -> bool:
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except (AttributeError, OSError):
        return False
    try:
        data = ctypes.c_int(value)
        result = dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), ctypes.c_int(attribute),
            ctypes.byref(data), ctypes.sizeof(data))
    except (AttributeError, OSError):
        return False
    return result == 0


def apply_dark_title_bar(window) -> bool:
    """Match the native title bar to the dark app; returns True on success."""
    if os.name != "nt":
        return False
    try:
        hwnd = int(window.winId())
    except (AttributeError, TypeError, ValueError):
        return False
    for attribute in (DWMWA_USE_IMMERSIVE_DARK_MODE,
                      DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY):
        if _set_attribute(hwnd, attribute, 1):
            return True
    return False


def apply_rounded_corners(window) -> bool:
    """Round window corners on Windows 11; a no-op elsewhere."""
    if os.name != "nt":
        return False
    try:
        hwnd = int(window.winId())
    except (AttributeError, TypeError, ValueError):
        return False
    return _set_attribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)


def apply_window_chrome(window) -> dict:
    """Apply every supported native tweak and report what worked."""
    return {
        "dark_title_bar": apply_dark_title_bar(window),
        "rounded_corners": apply_rounded_corners(window),
    }


def supported() -> bool:
    return os.name == "nt" and sys.platform != "cygwin"
