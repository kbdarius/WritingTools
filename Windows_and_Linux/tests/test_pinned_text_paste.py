import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

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


if __name__ == "__main__":
    unittest.main()
