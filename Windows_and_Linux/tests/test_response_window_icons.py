import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from ui.ResponseWindow import ResponseWindow


class FakeSignal:
    def connect(self, callback):
        self.callback = callback

    def disconnect(self, callback):
        if self.callback == callback:
            self.callback = None


class ResponseWindowIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_response_window_loads_icons_from_frozen_bundle_resources(self):
        app = SimpleNamespace(
            followup_response_signal=FakeSignal(),
            show_settings=lambda: None,
        )
        bundle_root = Path(__file__).resolve().parents[1]
        missing_executable = bundle_root / "missing" / "Writing Tools.exe"

        with (
            patch.object(sys, "_MEIPASS", str(bundle_root), create=True),
            patch.object(sys, "argv", [str(missing_executable)]),
        ):
            window = ResponseWindow(app, title="Rewrite Result")

        self.addCleanup(window.close)
        buttons = {
            button.toolTip(): button
            for button in window.findChildren(QtWidgets.QAbstractButton)
        }

        for tooltip in (
            "Zoom In",
            "Zoom Out",
            "Reset Zoom",
            "Copy latest rewrite",
            "Read Aloud",
            "Insert latest rewrite at cursor",
            "Send follow-up question",
        ):
            with self.subTest(tooltip=tooltip):
                self.assertIn(tooltip, buttons)
                self.assertFalse(buttons[tooltip].icon().isNull())


if __name__ == "__main__":
    unittest.main()
