"""Compact, non-activating controls for Read Aloud playback."""

from PySide6 import QtCore, QtGui, QtWidgets
from version import APP_VERSION


class SpeechControlWindow(QtWidgets.QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._closing_from_app = False
        self._drag_active = False
        self._drag_offset = QtCore.QPoint()
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
            "Previous sentence",
            self.app.previous_sentence_read_aloud,
        )
        self.pause_button = self._button(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPause),
            "Pause",
            self._toggle_pause,
        )
        self.forward_button = self._button(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaSeekForward),
            "Next sentence",
            self.app.next_sentence_read_aloud,
        )
        self.speed_button = QtWidgets.QToolButton()
        self.speed_button.setFixedSize(48, 34)
        self.speed_button.clicked.connect(self._cycle_speed)
        self.set_speed(self.app.get_read_aloud_rate())
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
            self.speed_button,
            self.settings_button,
            self.stop_button,
        ):
            layout.addWidget(button)

        self.version_label = QtWidgets.QLabel(f"v{APP_VERSION}")
        self.version_label.setStyleSheet(
            "color: #888; font-size: 10px; font-weight: bold; padding-left: 4px; padding-right: 2px;"
        )
        layout.addWidget(self.version_label)

        self.setStyleSheet(
            "SpeechControlWindow { background: #ffffff; border: 1px solid #b8b8b8; "
            "border-radius: 6px; }"
            "QToolButton { border: none; padding: 5px; border-radius: 3px; }"
            "QToolButton:hover { background: #e9e9e9; }"
            "QToolButton:pressed { background: #d6d6d6; }"
            "QToolButton:disabled { opacity: 0.4; }"
        )
        self.set_preparing("Preparing speech...")
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

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
        self.speed_button.setEnabled(False)

    def set_playing(self, message="Reading with Azure Speech..."):
        self.setToolTip(message)
        self.rewind_button.setEnabled(self.app.can_navigate_read_aloud())
        self.pause_button.setEnabled(self.app.can_pause_read_aloud())
        self.forward_button.setEnabled(self.app.can_navigate_read_aloud())
        self.speed_button.setEnabled(self.app.can_change_read_aloud_rate())
        self.set_speed(self.app.get_read_aloud_rate())
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

    def set_speed(self, rate):
        label = f"{rate:g}x"
        self.speed_button.setText(label)
        self.speed_button.setToolTip(
            f"Reading speed: {label}. Click to change."
        )

    def _cycle_speed(self):
        self.set_speed(self.app.cycle_read_aloud_rate())

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

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is None or child is self:
                self._drag_active = True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_active = False
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)
