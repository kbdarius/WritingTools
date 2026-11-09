"""Recover native Windows visibility when it differs from Qt's cached state."""

import ctypes
from ctypes import wintypes
import sys


def ensure_native_window_visible(window):
    """Restore a hidden native window even if QWidget.isVisible() is true."""
    if sys.platform != "win32":
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    handle = int(window.winId())
    if not user32.IsWindowVisible(handle):
        # show()/showNormal() can be no-ops when Qt already thinks the window
        # is visible. SW_RESTORE explicitly displays the native window.
        user32.ShowWindow(handle, 9)
        if not user32.IsWindowVisible(handle):
            raise RuntimeError("Windows did not display the Settings window")
