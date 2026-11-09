import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QAccessible
from aiprovider import TextSetting
from github_copilot_provider import GitHubCopilotProvider
from ui.CopilotSetupWidget import CopilotSetupWidget
from ui.SettingsWindow import SettingsWindow


class CopilotSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.provider = SimpleNamespace(settings=[
            TextSetting("github_account", default_value=""),
            TextSetting("model", default_value="gpt-5-mini"),
            TextSetting("reasoning_effort", default_value="medium"),
        ])
        self.provider.get_pending_config = lambda: {s.name: s.get_value() for s in self.provider.settings}
        with patch.object(QtCore.QTimer, "singleShot"):
            self.widget = CopilotSetupWidget(self.provider, {})
        self.addCleanup(self.widget.close)

    def test_discovery_keeps_unsaved_selection_and_reports_identity_on_catalog_failure(self):
        self.widget.controls["github_account"].setEditText("kbdarius")
        self.widget.controls["model"].setEditText("custom-model")
        generation = self.widget._generation
        self.widget._finish_refresh(generation, ["kbdarius", "KeivanDariusStrytenLLC"], {
            "authenticated": True, "login": "kbdarius", "auth_type": "token",
            "models": [], "error": "Model catalog blocked by network policy.",
        }, "")
        self.assertIn("Connected account: kbdarius", self.widget.status.text())
        self.assertIn("catalog blocked", self.widget.status.text())
        accessible = QAccessible.queryAccessibleInterface(self.widget.status)
        self.assertIn("kbdarius", accessible.text(QAccessible.Text.Name))
        self.assertIn("catalog blocked", accessible.text(QAccessible.Text.Name))
        self.assertEqual(self.provider.get_pending_config()["model"], "custom-model")
        self.assertEqual(self.provider.get_pending_config()["github_account"], "kbdarius")

    def test_late_discovery_from_previous_account_cannot_replace_current_status(self):
        old_generation = self.widget._generation
        self.widget.controls["github_account"].setEditText("KeivanDariusStrytenLLC")
        self.widget._finish_refresh(old_generation, ["kbdarius"], {
            "authenticated": True, "login": "kbdarius", "models": [{"id": "old-model"}],
        }, "")
        self.assertNotIn("Connected account: kbdarius", self.widget.status.text())
        self.assertEqual(self.widget.controls["model"].count(), 0)
        self.assertEqual(self.provider.get_pending_config()["github_account"], "KeivanDariusStrytenLLC")

    def test_typing_announces_changed_settings_once(self):
        with patch.object(QAccessible, "updateAccessibility") as announce:
            for text in ("a", "al", "ali", "alice"):
                self.widget.controls["github_account"].setEditText(text)
        self.assertEqual(announce.call_count, 1)

    def test_changing_accounts_clears_old_model_catalog_without_changing_choice(self):
        self.widget._finish_refresh(self.widget._generation, ["kbdarius"], {
            "authenticated": True, "login": "kbdarius", "models": [
                {"id": "gpt-5-mini", "reasoning_efforts": ["low", "medium"]},
            ],
        }, "")
        self.assertGreater(self.widget.controls["model"].count(), 0)
        self.widget.controls["github_account"].setEditText("another-account")
        self.assertEqual(self.widget.controls["model"].count(), 0)
        self.assertEqual(self.provider.get_pending_config()["model"], "gpt-5-mini")
        self.assertEqual(self.provider.get_pending_config()["reasoning_effort"], "medium")

    def test_scan_populates_model_picker_and_selection_uses_model_default_effort(self):
        self.widget._finish_refresh(self.widget._generation, ["kbdarius"], {
            "authenticated": True, "login": "kbdarius", "models": [
                {"id": "gpt-5-mini", "reasoning_efforts": ["medium"]},
                {"id": "another-model", "reasoning_efforts": []},
            ],
        }, "")
        picker = self.widget.controls["model"]
        self.assertEqual([picker.itemText(i) for i in range(picker.count())], ["gpt-5-mini", "another-model"])
        picker.setCurrentIndex(1)
        self.assertEqual(self.provider.get_pending_config()["model"], "another-model")
        self.assertEqual(self.provider.get_pending_config()["reasoning_effort"], "")

    def test_default_account_remains_empty_and_controls_have_accessible_names(self):
        self.widget._finish_refresh(self.widget._generation, ["kbdarius"], {
            "authenticated": True, "login": "kbdarius", "models": [],
        }, "")
        self.assertEqual(self.provider.get_pending_config()["github_account"], "")
        for combo in self.widget.controls.values():
            self.assertTrue(combo.accessibleName())
            self.assertTrue(combo.lineEdit().accessibleName())

    def test_actual_provider_reads_and_saves_the_displayed_unsaved_choices(self):
        app = SimpleNamespace(config={"providers": {}}, save_config=Mock())
        provider = GitHubCopilotProvider(app)
        with patch.object(QtCore.QTimer, "singleShot"):
            widget = CopilotSetupWidget(provider, {
                "github_account": "kbdarius", "model": "gpt-5-mini", "reasoning_effort": "medium",
            })
        self.addCleanup(widget.close)
        widget.controls["github_account"].setEditText("KeivanDariusStrytenLLC")
        widget.controls["reasoning_effort"].setEditText("")
        expected = {"github_account": "KeivanDariusStrytenLLC", "model": "gpt-5-mini", "reasoning_effort": ""}
        self.assertEqual(provider.get_pending_config(), expected)
        provider.save_config()
        self.assertEqual(app.config["providers"]["GitHub Copilot"], expected)
        self.assertEqual(set(expected), {"github_account", "model", "reasoning_effort"})

    def test_changed_settings_cannot_be_saved_using_an_earlier_validation(self):
        window = SimpleNamespace(
            _validation_in_progress=True, save_button=Mock(), provider_dropdown=Mock(),
            provider_test_button=Mock(), copilot_setup=None, validation_label=Mock(),
            _pending_provider=SimpleNamespace(provider_name="GitHub Copilot"),
            _pending_provider_config={"github_account": "kbdarius"},
            _current_provider_state=lambda: ("GitHub Copilot", {"github_account": "different"}),
            _validation_apply_after=True, _apply_settings=Mock(), _pending_options=None,
        )
        with patch.object(QtWidgets.QMessageBox, "warning"):
            SettingsWindow._finish_provider_validation(window, True, "Test passed")
        window._apply_settings.assert_not_called()
        self.assertIsNone(window._validated_provider_state)
        self.assertIn("Settings changed", window.validation_label.setText.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
