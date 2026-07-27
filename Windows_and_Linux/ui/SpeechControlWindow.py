"""Compact, non-activating controls for Read Aloud playback."""

from PySide6 import QtCore, QtGui, QtWidgets


class SpeechControlWindow(QtWidgets.QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._closing_from_app = False
        self.setWindowTitle("Read Aloud")
        self.setWindowFlags(
            QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedHeight(46)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(2)

        style = self.style()
        self.rewind_button = self._button(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaSeekBackward),
            "Rewind 10 seconds",
            lambda: self.app.seek_read_aloud(-10_000),
        )
        self.pause_button = self._button(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPause),
            "Pause",
            self._toggle_pause,
        )
        self.forward_button = self._button(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaSeekForward),
            "Forward 10 seconds",
            lambda: self.app.seek_read_aloud(10_000),
        )
        self.settings_button = self._button(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "Read Aloud voice settings",
            self.app.show_settings,
        )
        self.stop_button = self._button(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton),
            "Stop and close",
            self.app.cancel_read_aloud,
        )

        for button in (
            self.rewind_button,
            self.pause_button,
            self.forward_button,
            self.settings_button,
            self.stop_button,
        ):
            layout.addWidget(button)

        self.setStyleSheet(
            "SpeechControlWindow { background: #ffffff; border: 1px solid #b8b8b8; "
            "border-radius: 6px; }"
            "QToolButton { border: none; padding: 5px; border-radius: 3px; }"
            "QToolButton:hover { background: #e9e9e9; }"
            "QToolButton:pressed { background: #d6d6d6; }"
            "QToolButton:disabled { opacity: 0.4; }"
        )
        self.set_preparing("Preparing speech...")

    def _button(self, icon, tooltip, callback):
        button = QtWidgets.QToolButton()
        button.setIcon(icon)
        button.setIconSize(QtCore.QSize(21, 21))
        button.setFixedSize(34, 34)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        return button

    def set_preparing(self, message):
        self.setToolTip(message)
        self.rewind_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.forward_button.setEnabled(False)

    def set_playing(self, message="Reading with Azure Speech..."):
        self.setToolTip(message)
        self.rewind_button.setEnabled(self.app.can_seek_read_aloud())
        self.pause_button.setEnabled(self.app.can_pause_read_aloud())
        self.forward_button.setEnabled(self.app.can_seek_read_aloud())
        self.set_paused(False)

    def set_paused(self, paused):
        icon_name = (
            QtWidgets.QStyle.StandardPixmap.SP_MediaPlay
            if paused
            else QtWidgets.QStyle.StandardPixmap.SP_MediaPause
        )
        self.pause_button.setIcon(self.style().standardIcon(icon_name))
        self.pause_button.setToolTip("Resume" if paused else "Pause")

    def _toggle_pause(self):
        paused = self.app.pause_read_aloud()
        self.set_paused(paused)

    def close_without_cancel(self):
        """Close during normal cleanup without sending a second stop request."""
        self._closing_from_app = True
        self.close()

    def closeEvent(self, event):
        """Treat a user-initiated close as Stop, not just as hiding the window."""
        if not self._closing_from_app:
            self.app.cancel_read_aloud()
        super().closeEvent(event)

    def show_near_cursor(self):
        self.adjustSize()
        cursor = QtGui.QCursor.pos()
        screen = QtGui.QGuiApplication.screenAt(cursor) or QtGui.QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        x = min(max(cursor.x() - self.width() // 2, available.left()), available.right() - self.width())
        y = min(max(cursor.y() + 14, available.top()), available.bottom() - self.height())
        self.move(x, y)
        self.show()
