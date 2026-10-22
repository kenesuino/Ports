"""Overlay widgets layered above the terminal viewport.

They live in a parent container rather than inside the WebEngine view, so they
never intercept terminal keystrokes unless they are the focused control.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from .icons import icon
from .motion import fade_in
from .theme import DESTRUCTIVE, MOTION_TOAST, SPACE_1, SPACE_2, SPACE_3


def icon_button(glyph: str, tip: str, callback=None) -> QPushButton:
    widget = QPushButton()
    widget.setObjectName("iconBtn")
    widget.setIcon(icon(glyph))
    widget.setToolTip(tip)
    widget.setAccessibleName(tip)
    widget.setFixedSize(26, 26)
    if callback:
        widget.clicked.connect(callback)
    return widget


class FailureOverlay(QFrame):
    """Inline message when a shell exits or fails, with recovery actions."""

    restartRequested = pyqtSignal()
    retryRequested = pyqtSignal()
    closeRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("failureOverlay")
        self.setStyleSheet(
            f"QFrame#failureOverlay {{ background:#191919;"
            f" border:1px solid #3a2a2e; border-radius:8px; }}")
        self.setVisible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        self.title = QLabel("Terminal stopped")
        self.title.setStyleSheet(
            f"color:{DESTRUCTIVE}; font-size:13px; font-weight:600;")
        layout.addWidget(self.title)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("color:#b4b4b4;")
        layout.addWidget(self.detail)

        actions = QHBoxLayout()
        actions.setSpacing(SPACE_1)
        self.restart_button = QPushButton("Restart")
        self.restart_button.setObjectName("primary")
        self.restart_button.clicked.connect(self.restartRequested)
        self.retry_button = QPushButton("Retry launch")
        self.retry_button.clicked.connect(self.retryRequested)
        close_button = QPushButton("Close tab")
        close_button.clicked.connect(self.closeRequested)
        actions.addWidget(self.restart_button)
        actions.addWidget(self.retry_button)
        actions.addWidget(close_button)
        actions.addStretch(1)
        layout.addLayout(actions)

    def show_failure(self, session, disabled: bool = False) -> None:
        failed = session.state == "failed"
        self.title.setText("Launch failed" if failed else "Terminal exited")
        message = session.last_error or (
            "The shell exited. Restart re-runs its saved command; "
            "retry starts a fresh shell in the same folder.")
        self.detail.setText(message)
        self.restart_button.setVisible(bool(session.restart_cmd) and not failed)
        self.retry_button.setVisible(failed)
        fade_in(self, disabled=disabled)

    def hide_overlay(self) -> None:
        self.setVisible(False)


class SearchOverlay(QFrame):
    """Floating find bar, in the spirit of Windows Terminal and VS Code."""

    queryChanged = pyqtSignal(str)
    nextRequested = pyqtSignal()
    previousRequested = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchOverlay")
        self.setStyleSheet(
            "QFrame#searchOverlay { background:#1b1b1b;"
            " border:1px solid #282828; border-radius:8px; }")
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_2, SPACE_1, SPACE_1, SPACE_1)
        layout.setSpacing(SPACE_1)

        self.field = QLineEdit()
        self.field.setPlaceholderText("Find in terminal…")
        self.field.setAccessibleName("Find in terminal")
        self.field.setFixedWidth(220)
        self.field.textChanged.connect(self.queryChanged)
        self.field.returnPressed.connect(self.nextRequested)
        self.field.installEventFilter(self)
        layout.addWidget(self.field)

        self.count = QLabel("")
        self.count.setStyleSheet("color:#8e8e8e;")
        self.count.setMinimumWidth(52)
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.count)

        layout.addWidget(icon_button("chevron", "Previous match",
                                     self.previousRequested))
        layout.addWidget(icon_button("chevron-down", "Next match",
                                     self.nextRequested))
        layout.addWidget(icon_button("close", "Close search", self.dismissed))

    def set_count(self, match: int, total: int) -> None:
        self.count.setText(f"{match}/{total}" if total else "0/0")

    def open(self) -> None:
        self.setVisible(True)
        self.field.setFocus()
        self.field.selectAll()

    def close_search(self) -> None:
        self.field.clear()
        self.setVisible(False)

    def eventFilter(self, obj, event):
        if obj is self.field and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.dismissed.emit()
                return True
            if event.key() == Qt.Key.Key_Return and \
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.previousRequested.emit()
                return True
        return super().eventFilter(obj, event)


class ScrollToBottomPill(QPushButton):
    """Appears only while the terminal is scrolled up during live output."""

    def __init__(self, parent=None):
        super().__init__("Jump to latest", parent)
        self.setObjectName("chip")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Scroll terminal to latest output")
        self.setFixedHeight(24)
        self.setVisible(False)

    def set_scrolled_up(self, value: bool, disabled: bool = False) -> None:
        if value and not self.isVisible():
            fade_in(self, disabled=disabled)
        elif not value:
            self.setVisible(False)


class Toast(QFrame):
    """Single transient message anchored bottom-right of the terminal area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setStyleSheet(
            "QFrame#toast { background:#1b1b1b;"
            " border:1px solid #282828; border-radius:8px; }")
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_2, SPACE_3, SPACE_2)
        layout.setSpacing(SPACE_2)
        self.label = QLabel("")
        self.label.setStyleSheet("color:#e7e7e7;")
        layout.addWidget(self.label)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(MOTION_TOAST * 10)
        self._timer.timeout.connect(self.dismiss)

    def show_message(self, text: str, disabled: bool = False) -> None:
        self.label.setText(text)
        fade_in(self, MOTION_TOAST, disabled)
        self._timer.start()

    def dismiss(self) -> None:
        self._timer.stop()
        self.setVisible(False)
