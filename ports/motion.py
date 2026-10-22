"""Motion helpers: instant hover, state-only pulse, fading panels.

Hover is handled entirely by QSS ``:hover`` rules so no stylesheet is rewritten
per frame. Animation is reserved for transitions a person can name: a shell
starting, a first listener appearing, a panel opening, a toast arriving.
Everything is skipped when reduced motion is requested.
"""

from __future__ import annotations

import ctypes
import os

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, Qt, QVariantAnimation,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QPushButton, QWidget

from .theme import LISTENING, MOTION_PANEL, TEXT_DISABLED, WAITING


def reduced_motion(setting="system") -> bool:
    if setting in ("on", True):
        return True
    if setting in ("off", False):
        return False
    if os.name == "nt":
        try:
            enabled = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(
                    0x1042, 0, ctypes.byref(enabled), 0):
                return not bool(enabled.value)
        except (AttributeError, OSError):
            return False
    return False


_EASING = QEasingCurve(QEasingCurve.Type.OutCubic)


class HoverButton(QPushButton):
    """Button whose hover styling comes from the global stylesheet.

    Kept as a distinct type so callers and tests can identify controls that
    opt into QSS hover states rather than per-frame color animation.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.motion_disabled = False


class StatusDot(QWidget):
    """Small state indicator; pulses only while a state is transitional."""

    _RADIUS = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.setAccessibleName("Session status")
        self._state = "idle"
        self._ring = 0.0
        self.motion_disabled = False
        self._pulse = QVariantAnimation(self)
        self._pulse.setDuration(1400)
        self._pulse.setLoopCount(-1)
        self._pulse.setStartValue(0.0)
        self._pulse.setEndValue(1.0)
        self._pulse.valueChanged.connect(self._on_pulse)

    def set_state(self, state: str) -> None:
        self._state = state
        self.setToolTip(state.title())
        pulse = state in ("starting", "waiting")
        if pulse and not self.motion_disabled:
            if self._pulse.state() != QVariantAnimation.State.Running:
                self._pulse.start()
        else:
            self._pulse.stop()
            self._ring = 0.0
        self.update()

    def _on_pulse(self, value) -> None:
        self._ring = float(value)
        self.update()

    def _color(self) -> QColor:
        return QColor({
            "listening": LISTENING,
            "waiting": WAITING,
            "starting": WAITING,
            "failed": "#ff7b8a",
            "ready": TEXT_DISABLED,
        }.get(self._state, TEXT_DISABLED))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._color()
        if self._ring:
            ring = QColor(color)
            ring.setAlphaF(max(0.0, 0.45 * (1.0 - self._ring)))
            pen = QPen(ring)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            radius = self._RADIUS + 2.0 + self._ring * 3.0
            painter.drawEllipse(
                self.rect().center(),
                int(radius), int(radius))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(self.rect().center(), self._RADIUS, self._RADIUS)


def fade_in(widget: QWidget, duration: int = MOTION_PANEL,
            disabled: bool = False) -> None:
    """Show a widget with a short opacity fade, or instantly when disabled."""
    previous = getattr(widget, "_fade_animation", None)
    if previous is not None:
        previous.stop()
    widget.setVisible(True)
    effect = widget.graphicsEffect()
    if disabled or not isinstance(effect, QGraphicsOpacityEffect):
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        effect.setOpacity(1.0)
        return
    effect.setOpacity(0.0)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setEasingCurve(_EASING)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    widget._fade_animation = animation
    animation.start()


def expand(widget: QWidget, show: bool, disabled: bool = False) -> None:
    """Toggle a panel without animating height inside a splitter."""
    if show:
        fade_in(widget, MOTION_PANEL, disabled)
        return
    previous = getattr(widget, "_fade_animation", None)
    if previous is not None:
        previous.stop()
    widget.setVisible(False)
