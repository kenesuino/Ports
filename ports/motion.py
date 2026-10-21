"""Native motion with system preference and explicit override."""
import ctypes
import os

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QColor


def reduced_motion(setting="system"):
    if setting in ("on", True):
        return True
    if setting in ("off", False):
        return False
    if os.name == "nt":
        enabled = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return not bool(enabled.value)
    return False


class HoverButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        from PyQt6.QtCore import QVariantAnimation
        self._motion = QVariantAnimation(self)
        self._motion.setDuration(120)
        self._motion.valueChanged.connect(self._paint_color)
        self.motion_disabled = False

    def _paint_color(self, color):
        self.setStyleSheet(f"QPushButton{{background-color:{color.name()};}}")

    def _tint(self, enter):
        self._motion.stop()
        self._motion.setStartValue(self.palette().button().color())
        self._motion.setEndValue(QColor("#29354a" if enter else "#1a2434"))
        if self.motion_disabled:
            self._paint_color(self._motion.endValue())
        else:
            self._motion.start()

    def enterEvent(self, event):
        self._tint(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._tint(False)
        super().leaveEvent(event)


def expand(widget, show, disabled=False):
    previous = getattr(widget, "_expand_animation", None)
    if previous:
        previous.stop()
    if disabled:
        widget.setVisible(show)
        widget.setMaximumHeight(16777215 if show else 0)
        return
    widget.setVisible(True)
    animation = QPropertyAnimation(widget, b"maximumHeight", widget)
    animation.setDuration(180)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    target = min(280, max(80, widget.sizeHint().height())) if show else 0
    animation.setStartValue(widget.height())
    animation.setEndValue(target)
    if not show:
        animation.finished.connect(lambda: widget.setVisible(False))
    widget._expand_animation = animation
    animation.start()
