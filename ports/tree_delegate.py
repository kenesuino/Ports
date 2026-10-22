"""Tree delegate: one continuous selection band and a right-aligned clock.

A two-column QTreeWidget paints the selection per column, which leaves a
visible gap between the name and the elapsed-time column. This delegate paints
one rounded band across the full row and renders the duration as fixed-width
monospace so values never shift the layout.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate

from .theme import (
    BORDER, FOCUS, HOVER, MONO_FONT, PANEL, PRESSED, TEXT, TEXT_MUTED,
)


class TreeDelegate(QStyledItemDelegate):
    """Paints tree rows with a continuous selection band."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clock_font = QFont('Consolas', 9)
        self._clock_font.setStyleHint(QFont.StyleHint.Monospace)
        self._selected_rows: set = set()

    def set_selected_rows(self, rows) -> None:
        """Rows the tree considers selected, so the band spans both columns."""
        self._selected_rows = set(rows)

    def _is_selected(self, index) -> bool:
        tree = self.parent()
        if tree is None:
            return False
        try:
            item = tree.itemFromIndex(index)
        except (AttributeError, TypeError):
            item = None
        if item is None:
            # The delegate may receive a model index the tree cannot map back.
            # Fall back to matching the row's stable data role instead.
            data = index.data(Qt.ItemDataRole.UserRole)
            current = tree.currentItem()
            if data is None or current is None:
                return False
            return current.data(Qt.ItemDataRole.UserRole) == data
        current = tree.currentItem()
        return current is not None and current is item

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        option.state &= ~QStyle.StateFlag.State_Selected
        selected = self._is_selected(index)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

        widget = option.widget
        # If the tree does not draw its own row background (e.g. headless unit tests),
        # paint the background on column 0 only so column 1 doesn't overwrite it.
        if index.column() == 0 and not getattr(widget, '_has_draw_row_bg', False):
            if selected or hovered or focused:
                if selected:
                    background, border = QColor(HOVER), QColor(BORDER)
                elif focused:
                    background, border = QColor(PANEL), QColor(FOCUS)
                else:
                    background, border = QColor('#1b1b1b'), QColor('#202020')
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(border, 1))
                painter.setBrush(background)
                viewport = widget.viewport() if widget and hasattr(widget, 'viewport') else widget
                width = viewport.width() if viewport else option.rect.width()
                row_rect = QRect(4, option.rect.y() + 1, width - 8, option.rect.height() - 2)
                painter.drawRoundedRect(row_rect, 6, 6)

        column = index.column()
        text = index.data(Qt.ItemDataRole.DisplayRole) or ''
        if column == 1:
            painter.setFont(self._clock_font)
            painter.setPen(QPen(QColor(TEXT_MUTED)))
            rect = QRect(option.rect)
            rect.setLeft(rect.left() + 4)
            rect.setRight(rect.right() - 8)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter, str(text))
        else:
            font = index.data(Qt.ItemDataRole.FontRole)
            if font is not None:
                painter.setFont(font)
            is_heading = font is not None and font.bold()
            color = QColor(TEXT if (selected or is_heading) else TEXT_MUTED)
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            if icon is not None and not icon.isNull():
                size = QSize(16, 16)
                icon_rect = QRect(option.rect.left() + 2,
                                  option.rect.top() + (option.rect.height() - size.height()) // 2,
                                  size.width(), size.height())
                icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter,
                           QIcon.Mode.Normal, QIcon.State.Off)
                text_rect = QRect(option.rect)
                text_rect.setLeft(icon_rect.right() + 6)
                painter.setPen(QPen(color))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft
                                 | Qt.AlignmentFlag.AlignVCenter, str(text))
            else:
                painter.setPen(QPen(color))
                rect = QRect(option.rect)
                rect.setLeft(rect.left() + 4)
                painter.drawText(rect, Qt.AlignmentFlag.AlignLeft
                                 | Qt.AlignmentFlag.AlignVCenter, str(text))
        painter.restore()
