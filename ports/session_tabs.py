"""Top tab strip: session tabs plus a trailing new-terminal button."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTabBar, QWidget

from .icons import icon
from .theme import SPACE_1


class SessionTabs(QTabBar):
    selected = pyqtSignal(str)
    closeRequested = pyqtSignal(str)
    renameRequested = pyqtSignal(str)
    orderRequested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setExpanding(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setUsesScrollButtons(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Terminal tabs")
        self.currentChanged.connect(self._on_current)
        self.tabCloseRequested.connect(
            lambda index: self.closeRequested.emit(self.tabData(index)))
        self.tabBarDoubleClicked.connect(
            lambda index: self.renameRequested.emit(self.tabData(index))
            if index >= 0 else None)
        self.tabMoved.connect(
            lambda *_: self.orderRequested.emit(
                [self.tabData(i) for i in range(self.count())]))

    def _on_current(self, index: int) -> None:
        if index >= 0:
            self.selected.emit(self.tabData(index))

    def mousePressEvent(self, event):
        index = self.tabAt(event.position().toPoint())
        if index >= 0 and event.button() == Qt.MouseButton.MiddleButton:
            self.closeRequested.emit(self.tabData(index))
            event.accept()
            return
        super().mousePressEvent(event)

    def sync(self, sessions, active, unseen: set[str] | None = None) -> None:
        unseen = unseen or set()
        self.blockSignals(True)
        wanted = [s.id for s in sessions]
        for index in range(self.count() - 1, -1, -1):
            if self.tabData(index) not in wanted:
                self.removeTab(index)
        for position, session in enumerate(sessions):
            index = next((i for i in range(self.count())
                          if self.tabData(i) == session.id), -1)
            if index < 0:
                index = self.addTab(session.name)
                self.setTabData(index, session.id)
                close = QPushButton(self)
                close.setObjectName('tabCloseButton')
                close.setIcon(icon('close', '#aaaaaa', 14))
                close.setIconSize(QSize(14, 14))
                close.setFixedSize(24, 24)
                close.setCursor(Qt.CursorShape.PointingHandCursor)
                close.setAccessibleName('Close terminal tab')
                close.setToolTip('Close terminal (Ctrl+W)')
                close.setStyleSheet('QPushButton#tabCloseButton {background:transparent; border:1px solid transparent; border-radius:5px; padding:0;} QPushButton#tabCloseButton:hover {background:#353535; border-color:#4a4a4a;} QPushButton#tabCloseButton:pressed {background:#454545;} QPushButton#tabCloseButton:focus {border-color:#c8c8c8;}')
                close.clicked.connect(lambda _=False, sid=session.id: self.closeRequested.emit(sid))
                # Replace both platform-specific defaults so close is stable
                # across Qt styles, scaling and tab reorder.
                self.setTabButton(index, QTabBar.ButtonPosition.LeftSide, None)
                self.setTabButton(index, QTabBar.ButtonPosition.RightSide, close)
            if index != position:
                self.moveTab(index, position)
            ports = sorted({item.port for item in session.listeners})
            prefix = "● " if session.id in unseen and session is not active else ""
            suffix = "  " + " ".join(f":{p}" for p in ports[:2]) if ports else ""
            instances = list(dict.fromkeys(getattr(s, 'instance_id', '') for s in sessions if s.profile_id == session.profile_id))
            copy_label = f" · {instances.index(session.instance_id) + 1}" if len(instances) > 1 and getattr(session, 'instance_id', '') in instances else ''
            self.setTabText(position, prefix + session.name + copy_label + suffix)
            self.setTabIcon(position, icon("terminal"))
            tip = [f"{session.name} — {session.shell} · {session.state}",
                   session.current_cwd or session.cwd or "shell home"]
            if session.last_error:
                tip.append(f"Error: {session.last_error}")
            self.setTabToolTip(position, "\n".join(tip))
            if session is active:
                self.setCurrentIndex(position)
        self.blockSignals(False)


class TabStrip(QWidget):
    """Tabs plus the new-terminal affordance, matching the header row."""

    newTerminalRequested = pyqtSignal()
    selected = pyqtSignal(str)
    closeRequested = pyqtSignal(str)
    renameRequested = pyqtSignal(str)
    orderRequested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tabStrip")
        self.setFixedHeight(34)
        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE_1, 0, SPACE_1, 0)
        row.setSpacing(SPACE_1)
        self.tabs = SessionTabs(self)
        row.addWidget(self.tabs, 1)
        self.add_button = QPushButton()
        self.add_button.setObjectName("iconBtn")
        self.add_button.setIcon(icon("add"))
        self.add_button.setToolTip("New terminal  (Ctrl+Shift+T)")
        self.add_button.setAccessibleName("New terminal")
        self.add_button.setFixedSize(26, 26)
        self.add_button.clicked.connect(self.newTerminalRequested)
        row.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.tabs.selected.connect(self.selected)
        self.tabs.closeRequested.connect(self.closeRequested)
        self.tabs.renameRequested.connect(self.renameRequested)
        self.tabs.orderRequested.connect(self.orderRequested)
        self._overflow = False

    def sync(self, sessions, active, unseen=None) -> None:
        self.tabs.sync(sessions, active, unseen)
        self._update_overflow()

    def _update_overflow(self) -> None:
        """Fade the strip edges only while the tabs overflow the available width."""
        needed = sum(self.tabs.tabRect(i).width() for i in range(self.tabs.count()))
        overflow = needed > self.tabs.width()
        if overflow == self._overflow:
            return
        self._overflow = overflow
        self.tabs.setProperty("overflow", "true" if overflow else "false")
        self.tabs.style().unpolish(self.tabs)
        self.tabs.style().polish(self.tabs)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_overflow()

    def current_session_id(self) -> str:
        return self.tabs.tabData(self.tabs.currentIndex()) or ""
