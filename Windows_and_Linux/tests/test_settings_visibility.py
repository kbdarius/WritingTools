"""Native Windows regressions, isolated from the suite's offscreen QApplication."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32", "Requires native Windows HWNDs")
class SettingsVisibilityTests(unittest.TestCase):
    def run_native_case(self, case):
        env = os.environ.copy()
        # Other tests select offscreen before importing Qt. A fresh process and
        # an explicit override are essential to exercise real Windows visibility.
        env["QT_QPA_PLATFORM"] = "windows"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--native-case", case],
            cwd=APP_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode, 0,
            f"Native case {case!r} failed:\n{result.stdout}\n{result.stderr}",
        )
        self.assertIn(f"PASS: {case}", result.stdout)

    def test_helper_repairs_native_hidden_qt_visible_window(self):
        self.run_native_case("helper")

    def test_open_settings_restores_existing_native_hidden_window(self):
        self.run_native_case("open_settings")

    def test_deferred_settings_open_restores_window_and_selects_pinned_text(self):
        self.run_native_case("pinned_text")


def run_native_case(case):
    """Run only in a disposable process; never initialize the full app/hotkeys."""
    import ctypes
    from ctypes import wintypes
    import time
    from types import SimpleNamespace
    from unittest.mock import Mock

    os.environ["QT_QPA_PLATFORM"] = "windows"
    sys.path.insert(0, str(APP_ROOT))
    from PySide6 import QtWidgets
    from ui.window_visibility import ensure_native_window_visible

    check = unittest.TestCase()
    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    check.assertEqual(app.platformName(), "windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL

    def settle():
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

    class SettingsFixture(QtWidgets.QWidget):
        # Real native window and tabs; provider/configuration UI is irrelevant
        # to recovery of an existing Settings window and could access user data.
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Writing Tools disposable visibility test")
            self.tabs = QtWidgets.QTabWidget(self)
            self.tabs.addTab(QtWidgets.QWidget(), "General")
            self.pinned_page = QtWidgets.QWidget()
            self.tabs.addTab(self.pinned_page, "Pinned Text")
            layout = QtWidgets.QVBoxLayout(self)
            layout.addWidget(self.tabs)
            self.resize(420, 180)
            frame = self.frameGeometry()
            frame.moveCenter(app.primaryScreen().availableGeometry().center())
            self.move(frame.topLeft())

        def select_tab(self, name):
            check.assertEqual(name, "pinned_text")
            self.tabs.setCurrentWidget(self.pinned_page)

    window = SettingsFixture()
    popup = QtWidgets.QWidget()
    try:
        window.show()
        hwnd = wintypes.HWND(int(window.winId()))
        # Establish a visible baseline even if the test runner was launched
        # with hidden startup mode. Subsequent SW_HIDE creates the regression.
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        settle()
        check.assertTrue(window.isVisible())
        check.assertTrue(user32.IsWindowVisible(hwnd))

        user32.ShowWindow(hwnd, 0)  # SW_HIDE, bypassing Qt's cached state
        settle()
        check.assertTrue(window.isVisible(), "Native hide must leave Qt visible")
        check.assertFalse(user32.IsWindowVisible(hwnd))

        # Negative control: the previous opening sequence cannot repair this.
        window.showNormal()
        window.show()
        window.raise_()
        window.activateWindow()
        settle()
        check.assertTrue(window.isVisible())
        check.assertFalse(
            user32.IsWindowVisible(hwnd),
            "Qt-only sequence unexpectedly recovered; reassess this regression",
        )

        if case == "helper":
            ensure_native_window_visible(window)
        else:
            from WritingToolApp import WritingToolApp

            popup.show()
            state = SimpleNamespace(
                settings_window=window,
                popup_window=popup,
                show_message_signal=SimpleNamespace(emit=Mock()),
            )
            state._open_settings_window = lambda *args: (
                WritingToolApp._open_settings_window(state, *args)
            )
            if case == "open_settings":
                WritingToolApp._open_settings_window(state)
            elif case == "pinned_text":
                WritingToolApp.show_settings(state, settings_tab="pinned_text")
            else:
                raise AssertionError(f"Unknown native case: {case}")
            settle()
            state.show_message_signal.emit.assert_not_called()
            check.assertIs(state.settings_window, window, "Reuse the existing window")
            check.assertFalse(popup.isVisible())
            if case == "pinned_text":
                check.assertIs(window.tabs.currentWidget(), window.pinned_page)

        settle()
        check.assertEqual(int(window.winId()), hwnd.value, "Restore the same HWND")
        check.assertTrue(window.isVisible())
        check.assertTrue(user32.IsWindowVisible(hwnd), "Native window must be shown")
        # Reopening an already visible window must remain safe.
        ensure_native_window_visible(window)
        check.assertTrue(user32.IsWindowVisible(hwnd))
        print(f"PASS: {case}", flush=True)
    finally:
        popup.close()
        window.close()
        app.processEvents()
        app.quit()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--native-case":
        run_native_case(sys.argv[2])
    else:
        unittest.main()
