"""Alternative top-tab selector over existing, persistent terminal views."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QMenu, QTabBar

from .icons import icon


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
        self.currentChanged.connect(lambda i: self.selected.emit(self.tabData(i)) if i >= 0 else None)
        self.tabCloseRequested.connect(lambda i: self.closeRequested.emit(self.tabData(i)))
        self.tabBarDoubleClicked.connect(lambda i: self.renameRequested.emit(self.tabData(i)) if i >= 0 else None)
        self.tabMoved.connect(lambda *_: self.orderRequested.emit([self.tabData(i) for i in range(self.count())]))
        self.setAccessibleName("Terminal tabs")

    def sync(self, sessions, active):
        self.blockSignals(True)
        wanted = [s.id for s in sessions]
        for i in range(self.count() - 1, -1, -1):
            if self.tabData(i) not in wanted:
                self.removeTab(i)
        for position, session in enumerate(sessions):
            index = next((i for i in range(self.count()) if self.tabData(i) == session.id), -1)
            if index < 0:
                index = self.addTab(session.name)
                self.setTabData(index, session.id)
            if index != position:
                self.moveTab(index, position)
            ports = sorted({l.port for l in session.listeners})
            suffix = " " + " ".join(f":{p}" for p in ports[:2]) if ports else ""
            self.setTabText(position, session.name + suffix)
            self.setTabIcon(position, icon("terminal", session.accent))
            self.setTabToolTip(position, f"{session.name}\n{session.shell} · {session.state}\n{session.current_cwd or session.cwd}")
            if session is active:
                self.setCurrentIndex(position)
        self.blockSignals(False)
