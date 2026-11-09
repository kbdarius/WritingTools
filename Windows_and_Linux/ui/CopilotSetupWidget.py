"""Account discovery and preflight controls for the Copilot provider."""

import asyncio
import os
import shutil
import subprocess
import threading
import webbrowser

from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QAccessible, QAccessibleEvent

from aiprovider import NoWheelComboBox


class ConnectionStatusLabel(QtWidgets.QLabel):
    """Expose asynchronous account/error text to assistive technology."""

    def setText(self, text):
        if text == self.text():
            return
        super().setText(text)
        self.setAccessibleName("Copilot connection status: " + text)
        QAccessible.updateAccessibility(QAccessibleEvent(self, QAccessible.Event.Alert))


class CopilotSetupWidget(QtWidgets.QWidget):
    refreshed = QtCore.Signal(int, object, object, str)

    def __init__(self, provider, config, parent=None):
        super().__init__(parent)
        self.provider = provider
        self._generation = 0
        self._models = []
        self._refreshing = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.controls = {}
        labels = {
            "github_account": "GitHub &account:",
            "model": "Copilot &model:",
            "reasoning_effort": "&Reasoning effort:",
        }
        for setting in provider.settings:
            combo = NoWheelComboBox()
            combo.setEditable(True)
            combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
            combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(18)
            combo.setAccessibleName(labels[setting.name].replace("&", "").rstrip(":"))
            combo.lineEdit().setAccessibleName(combo.accessibleName())
            combo.setEditText(str(config.get(setting.name, setting.default_value) or ""))
            label = QtWidgets.QLabel(labels[setting.name])
            label.setBuddy(combo)
            layout.addWidget(label)
            layout.addWidget(combo)
            setting.input = combo.lineEdit()
            self.controls[setting.name] = combo

        self.controls["github_account"].lineEdit().setPlaceholderText("Automatic (current Copilot sign-in)")
        self.controls["github_account"].setToolTip("Select a stored GitHub account or enter its login. This does not switch the account used by other apps.")
        self.controls["model"].setToolTip("Scan your account, then open this dropdown to choose an available model. You can also enter a model ID. Test it before saving.")
        self.controls["reasoning_effort"].lineEdit().setPlaceholderText("Model default")
        self.controls["reasoning_effort"].setToolTip("Leave blank for the model default. Refresh lists supported efforts for the selected model.")

        self.status = ConnectionStatusLabel()
        self.status.setText("Account not checked yet.")
        self.status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.status.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.status)
        self.refresh_button = QtWidgets.QPushButton("Scan account for available models")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        self.sign_in_button = QtWidgets.QPushButton("Sign in / add GitHub account…")
        self.sign_in_button.clicked.connect(self.show_sign_in)
        layout.addWidget(self.sign_in_button)
        note = QtWidgets.QLabel(
            "Scan your account, then choose a model from the dropdown above. "
            "Scanning checks sign-in and model access without sending a prompt. "
            "Test writing AI connection sends one short sample and uses your Copilot allowance. "
            "Saving changed connection settings also tests them unless they already passed. "
            "Writing Tools stores your account and model choices, never the GitHub token."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.controls["github_account"].editTextChanged.connect(self._account_changed)
        self.controls["model"].editTextChanged.connect(self._model_changed)
        self.controls["reasoning_effort"].editTextChanged.connect(self._settings_changed)
        self.refreshed.connect(self._finish_refresh)
        QtCore.QTimer.singleShot(0, self.refresh)

    def _settings_changed(self):
        self.status.setText("Settings changed. Scan account for available models, then test this connection.")

    def invalidate_refresh(self):
        """Ignore a discovery result that predates a real connection test."""
        self._generation += 1

    def _account_changed(self):
        self._generation += 1
        self._models = []
        self._replace_items(self.controls["model"], [])
        self._replace_items(self.controls["reasoning_effort"], [])
        self._settings_changed()

    def _model_changed(self):
        model_id = self.controls["model"].currentText().strip()
        model = next((item for item in self._models if item["id"] == model_id), None)
        effort = self.controls["reasoning_effort"]
        if model is not None and effort.currentText() not in (model.get("reasoning_efforts") or []):
            effort.setEditText("")
        self._update_efforts()
        self._settings_changed()

    @staticmethod
    def _replace_items(combo, values):
        text = combo.currentText()
        blocker = QtCore.QSignalBlocker(combo)
        combo.clear()
        combo.addItems(list(dict.fromkeys(values)))
        combo.setEditText(text)
        del blocker

    def _update_efforts(self):
        model_id = self.controls["model"].currentText().strip()
        model = next((item for item in self._models if item["id"] == model_id), {})
        self._replace_items(self.controls["reasoning_effort"], [""] + (model.get("reasoning_efforts") or []))

    def refresh(self):
        if self._refreshing or not self.isEnabled():
            return
        self._refreshing = True
        self._generation += 1
        generation = self._generation
        config = self.provider.get_pending_config().copy()
        self.refresh_button.setEnabled(False)
        self.status.setText("Scanning the selected account for available models…")

        def worker():
            accounts, account_error = [], ""
            try:
                accounts = self.provider.list_accounts()
            except (Exception, asyncio.CancelledError):
                account_error = "Stored account list could not be loaded. Use Sign in / add GitHub account, then scan again."
            try:
                result = self.provider.inspect_connection(config)
            except (Exception, asyncio.CancelledError):
                result = {"error": "Could not scan the Copilot account. Try scanning again."}
            try:
                self.refreshed.emit(generation, accounts, result, account_error)
            except RuntimeError:
                pass  # The Settings window was closed while the check completed.

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.Slot(int, object, object, str)
    def _finish_refresh(self, generation, accounts, result, account_error):
        self._refreshing = False
        self.refresh_button.setEnabled(True)
        if generation != self._generation:
            return
        self._replace_items(self.controls["github_account"], [""] + accounts)
        self._models = result.get("models", [])
        self._replace_items(self.controls["model"], [item["id"] for item in self._models])
        self._update_efforts()
        if result.get("authenticated"):
            identity = result.get("login") or "identity unavailable"
            message = f"Connected account: {identity}"
            if result.get("auth_type"):
                message += f" ({result['auth_type']})"
            message += "."
        else:
            message = "Copilot account is not verified."
        if result.get("error"):
            message += "\n" + result["error"]
            message += "\nThe model list could not be loaded. You can still enter a model ID and test it."
        elif result.get("authenticated"):
            message += f"\nScan found {len(self._models)} models. Choose one from the Copilot model dropdown, then test the connection."
        if account_error:
            message += "\n" + account_error
        self.status.setText(message)

    def show_sign_in(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Connect a GitHub account")
        dialog.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(dialog)
        instructions = QtWidgets.QLabel(
            "Sign in with the GitHub account whose Copilot subscription you want to use. "
            "Repeat for another account if needed. GitHub CLI securely stores the credentials.\n\n"
            "After sign-in, close the terminal, return here, and choose Scan account for available models. "
            "Select the account, choose a model, then Test writing AI connection. "
            "Signing in may change GitHub CLI's active account; choosing an account in Writing Tools does not."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        command = QtWidgets.QLineEdit("gh auth login --hostname github.com --web")
        command.setReadOnly(True)
        command.setAccessibleName("GitHub sign-in command")
        layout.addWidget(command)
        start = QtWidgets.QPushButton("Open sign-in terminal")
        start.clicked.connect(lambda: self._launch_sign_in(dialog))
        layout.addWidget(start)
        guide = QtWidgets.QPushButton("GitHub CLI installation guide")
        guide.clicked.connect(lambda: webbrowser.open("https://cli.github.com/"))
        layout.addWidget(guide)
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    @staticmethod
    def _launch_sign_in(parent):
        gh_path = shutil.which("gh")
        if not gh_path:
            QtWidgets.QMessageBox.warning(parent, "GitHub CLI required", "Install GitHub CLI using the installation guide, then reopen Writing Tools and try again.")
            return
        if os.name != "nt":
            QtWidgets.QMessageBox.information(parent, "GitHub sign-in", "Run the command shown above in your terminal, then refresh accounts.")
            return
        # Interactive terminal explicitly requested by the Sign-in button.
        excluded = {"GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
                    "GITHUB_ENTERPRISE_TOKEN", "GH_DEBUG", "GH_PROMPT_DISABLED"}
        env = {key: value for key, value in os.environ.items() if key.upper() not in excluded}
        try:
            subprocess.Popen([gh_path, "auth", "login", "--hostname", "github.com", "--web"], env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except OSError:
            QtWidgets.QMessageBox.warning(parent, "Could not open sign-in", "Run the command shown above in your terminal, then refresh accounts.")
