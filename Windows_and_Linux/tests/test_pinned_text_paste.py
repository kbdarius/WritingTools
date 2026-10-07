import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

import WritingToolApp as writing_tool_app_module
from WritingToolApp import WritingToolApp
from ui.CustomPopupWindow import CustomPopupWindow


class PinnedTextPasteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_selection_hides_popup_before_restoring_target_and_pasting(self):
        popup = QtWidgets.QWidget()
        self.addCleanup(popup.close)
        popup.show()
        popup.app = Mock()
        popup.app._restore_target_and_paste.side_effect = (
            lambda text: self.assertFalse(popup.isVisible())
        )

        CustomPopupWindow.paste_pinned_text(popup, "Saved text")

        popup.app._restore_target_and_paste.assert_called_once_with("Saved text")

    def test_paste_delays_clipboard_restore_until_after_target_can_read_it(self):
        clipboard = {"text": "Original clipboard"}
        scheduled_callbacks = []
        keyboard = Mock()

        with (
            unittest.mock.patch.object(
                writing_tool_app_module.pyperclip,
                "paste",
                side_effect=lambda: clipboard["text"],
            ),
            unittest.mock.patch.object(
                writing_tool_app_module.pyperclip,
                "copy",
                side_effect=lambda text: clipboard.update(text=text),
            ),
            unittest.mock.patch.object(
                writing_tool_app_module.pykeyboard,
                "Controller",
                return_value=keyboard,
            ),
            unittest.mock.patch.object(
                writing_tool_app_module.QtCore.QTimer,
                "singleShot",
                side_effect=lambda delay, callback: scheduled_callbacks.append(
                    (delay, callback)
                ),
            ),
        ):
            WritingToolApp._paste_text_at_cursor("Saved text\n")

            self.assertEqual(clipboard["text"], "Saved text")
            self.assertEqual(len(scheduled_callbacks), 1)
            self.assertEqual(scheduled_callbacks[0][0], 1000)
            scheduled_callbacks[0][1]()

        self.assertEqual(clipboard["text"], "Original clipboard")

    def test_paste_does_not_overwrite_clipboard_changed_by_target(self):
        clipboard = {"text": "Original clipboard"}
        scheduled_callbacks = []
        keyboard = Mock()

        with (
            unittest.mock.patch.object(
                writing_tool_app_module.pyperclip,
                "paste",
                side_effect=lambda: clipboard["text"],
            ),
            unittest.mock.patch.object(
                writing_tool_app_module.pyperclip,
                "copy",
                side_effect=lambda text: clipboard.update(text=text),
            ),
            unittest.mock.patch.object(
                writing_tool_app_module.pykeyboard,
                "Controller",
                return_value=keyboard,
            ),
            unittest.mock.patch.object(
                writing_tool_app_module.QtCore.QTimer,
                "singleShot",
                side_effect=lambda delay, callback: scheduled_callbacks.append(
                    (delay, callback)
                ),
            ),
        ):
            WritingToolApp._paste_text_at_cursor("Saved text")
            clipboard["text"] = "Changed by target"
            scheduled_callbacks[0][1]()

        self.assertEqual(clipboard["text"], "Changed by target")


if __name__ == "__main__":
    unittest.main()
