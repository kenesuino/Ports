"""Native chrome drawing for combo and tree chevrons.

Qt stylesheets resolve ``url(...)`` relative to the process working
directory, so a packaged or differently-launched app loses the icons and logs
"qt.svg: Cannot open file". Drawing the chevrons in a style proxy removes the
file dependency entirely and keeps one consistent mark everywhere.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QComboBox, QProxyStyle, QStyle

from .theme import TEXT, TEXT_MUTED


class PortsStyle(QProxyStyle):
    """Draws a neutral chevron for combo boxes and tree branches."""

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorBranch:
            if not (option.state & QStyle.StateFlag.State_Children):
                return
            self._chevron(painter, option,
                           bool(option.state & QStyle.StateFlag.State_Open))
            return
        if element == QStyle.PrimitiveElement.PE_IndicatorArrowDown:
            if isinstance(widget, QComboBox):
                self._chevron(painter, option, True)
                return
        if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
            return
        super().drawPrimitive(element, option, painter, widget)

    def _chevron(self, painter, option, expanded: bool) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(TEXT if option.state & QStyle.StateFlag.State_MouseOver
                      else TEXT_MUTED)
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        rect = QRectF(option.rect)
        center_x, center_y = rect.center().x(), rect.center().y()
        arm = 3.5
        path = QPainterPath()
        if expanded:
            path.moveTo(QPointF(center_x - arm, center_y - arm / 2))
            path.lineTo(QPointF(center_x, center_y + arm / 2))
            path.lineTo(QPointF(center_x + arm, center_y - arm / 2))
        else:
            path.moveTo(QPointF(center_x - arm / 2, center_y - arm))
            path.lineTo(QPointF(center_x + arm / 2, center_y))
            path.lineTo(QPointF(center_x - arm / 2, center_y + arm))
        painter.drawPath(path)
        painter.restore()
