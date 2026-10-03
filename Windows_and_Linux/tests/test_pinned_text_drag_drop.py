import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from ui.CustomPopupWindow import CustomPopupWindow, PinnedTextTreeWidget
from ui.SettingsWindow import PinnedTextSettingsPanel


class PinnedTextDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "pinned_texts.json"
        self.path.write_text(json.dumps([
            {"label": "First", "text": "First example", "group": "A"},
            {"label": "Second", "text": "Second example", "group": "A"},
            {"label": "Third", "text": "Third example", "group": "A"},
            {"label": "Fourth", "text": "Fourth example", "group": "B"},
            {"label": "Solo", "text": "Solo example", "group": ""},
        ]), encoding="utf-8")
        path_patch = patch.object(CustomPopupWindow, "pinned_texts_path", return_value=str(self.path))
        path_patch.start()
        self.addCleanup(path_patch.stop)
        self.panel = PinnedTextSettingsPanel()
        self.addCleanup(self.panel.close)
        self.tree = self.panel.list_widget
        self.tree.resize(500, 350)
        self.tree.show()
        self.app.processEvents()
        self.signals = []
        self.tree.items_reordered.connect(lambda: self.signals.append(True))

    def item(self, name):
        return self.tree.findItems(name, QtCore.Qt.MatchFlag.MatchExactly | QtCore.Qt.MatchFlag.MatchRecursive)[0]

    def drop(self, name, target_name=None, after=False, indicator=None):
        dragged = self.item(name)
        self.tree.setCurrentItem(dragged)
        target = self.item(target_name) if target_name else None
        if target is None:
            point = QtCore.QPoint(100, self.tree.viewport().height() - 5)
        else:
            rect = self.tree.visualItemRect(target)
            point = QtCore.QPoint(rect.center().x(), rect.bottom() - 1 if after else rect.top() + 1)
        event = QtGui.QDropEvent(
            QtCore.QPointF(point), QtCore.Qt.DropAction.MoveAction,
            QtCore.QMimeData(), QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        position = indicator or (
            QtWidgets.QAbstractItemView.DropIndicatorPosition.BelowItem if after
            else QtWidgets.QAbstractItemView.DropIndicatorPosition.AboveItem
        )
        with patch.object(PinnedTextTreeWidget, "dropIndicatorPosition", return_value=position):
            self.tree.dropEvent(event)
        self.app.processEvents()
        return event

    def labels(self):
        return [entry["label"] for entry in self.panel.entries]

    def test_move_item_up_accepts_drop_and_persists(self):
        event = self.drop("Third", "First")
        self.assertTrue(event.isAccepted())
        self.assertEqual(event.dropAction(), QtCore.Qt.DropAction.MoveAction)
        self.assertEqual(self.labels(), ["Third", "First", "Second", "Fourth", "Solo"])
        self.assertEqual(len(self.signals), 1)
        self.assertEqual(self.tree.currentItem().text(0), "Third")
        self.panel.entries = CustomPopupWindow.load_pinned_texts()
        self.panel._refresh()
        self.assertEqual(self.item("A").child(0).text(0), "Third")

    def test_move_item_down(self):
        self.drop("First", "Third", after=True)
        self.assertEqual(self.labels(), ["Second", "Third", "First", "Fourth", "Solo"])

    def test_drag_lifecycle_does_not_remove_the_moved_selection(self):
        self.tree.setCurrentItem(self.item("Third"))
        with patch("ui.CustomPopupWindow.QtGui.QDrag") as drag_class:
            drag_class.return_value.exec.side_effect = lambda *args: (
                self.drop("Third", "First").dropAction()
            )
            self.tree.startDrag(QtCore.Qt.DropAction.MoveAction)
        drag_class.assert_called_once_with(self.tree)
        drag_class.return_value.exec.assert_called_once_with(
            QtCore.Qt.DropAction.MoveAction, QtCore.Qt.DropAction.MoveAction,
        )
        self.assertEqual(self.item("A").childCount(), 3)
        self.assertEqual(self.labels(), ["Third", "First", "Second", "Fourth", "Solo"])
        self.assertEqual(self.tree.currentItem().text(0), "Third")

    def test_move_item_onto_category(self):
        self.drop("Second", "B", indicator=QtWidgets.QAbstractItemView.DropIndicatorPosition.OnItem)
        self.assertEqual(self.item("Second").parent().text(0), "B")
        saved = CustomPopupWindow.load_pinned_texts()
        self.assertEqual(next(entry for entry in saved if entry["label"] == "Second")["group"], "B")

    def test_move_item_relative_to_another_category_child(self):
        self.drop("Second", "Fourth")
        self.assertEqual(self.item("B").child(0).text(0), "Second")
        self.assertEqual(self.labels(), ["First", "Third", "Second", "Fourth", "Solo"])

    def test_move_categories_up_and_down_without_nesting(self):
        self.drop("B", "A")
        self.assertEqual(self.tree.topLevelItem(0).text(0), "B")
        self.drop("B", "Third", after=True)
        self.assertEqual(self.tree.topLevelItem(0).text(0), "A")
        self.assertIsNone(self.item("B").parent())
        self.assertEqual(self.labels(), ["First", "Second", "Third", "Fourth", "Solo"])

    def test_category_cannot_be_dropped_into_its_own_child(self):
        before = copy.deepcopy(self.panel.entries)
        event = self.drop("A", "Second")
        self.assertFalse(event.isAccepted())
        self.assertEqual(self.panel.entries, before)
        self.assertFalse(self.signals)

    def test_same_item_drop_does_not_change_data(self):
        before = copy.deepcopy(self.panel.entries)
        event = self.drop("Second", "Second")
        self.assertFalse(event.isAccepted())
        self.assertEqual(self.panel.entries, before)

    def test_empty_space_makes_item_ungrouped(self):
        self.drop("Second")
        self.assertIsNone(self.item("Second").parent())
        self.assertEqual(self.panel.entries[-1]["group"], "")
        self.assertEqual(len(self.panel.entries), 5)

    def test_move_last_child_preserves_other_items_on_reload(self):
        self.drop("Fourth", "A", indicator=QtWidgets.QAbstractItemView.DropIndicatorPosition.OnItem)
        saved = CustomPopupWindow.load_pinned_texts()
        self.assertEqual(len(saved), 5)
        self.assertEqual(next(entry for entry in saved if entry["label"] == "Fourth")["group"], "A")
        self.panel.entries = saved
        self.panel._refresh()
        self.assertEqual(self.item("A").childCount(), 4)


if __name__ == "__main__":
    unittest.main()
