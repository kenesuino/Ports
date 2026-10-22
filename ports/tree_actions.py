"""One viewport-owned action strip shared by hovered/focused terminal rows."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton
from .icons import icon


class TerminalRowActions(QFrame):
    triggered = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('terminalRowActions')
        self.setStyleSheet('QFrame#terminalRowActions {background:#242424; border-radius:4px;}')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)
        self.buttons = {}
        for action, glyph, title in (
            ('start', 'run', 'Start this terminal'),
            ('retry', 'retry', 'Retry this shell'),
            ('edit', 'edit', 'Edit saved terminal definition'),
            ('close', 'close', 'Close this terminal'),
        ):
            button = QPushButton(self)
            button.setObjectName('rowAction')
            button.setIcon(icon(glyph, size=16))
            button.setFixedSize(24, 28)
            button.setAccessibleName(title)
            button.setToolTip(title)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, value=action: self.triggered.emit(value))
            layout.addWidget(button)
            self.buttons[action] = button
        self.hide()

    def configure(self, row):
        session = row.get('session')
        visible = {
            'start': session is None,
            'retry': session is not None and row.get('state') in ('failed', 'exited'),
            'edit': row.get('definition') is not None,
            'close': session is not None,
        }
        for action, button in self.buttons.items():
            button.setVisible(visible[action])
        self.setFixedSize(4 + 24 * sum(visible.values()), 28)
