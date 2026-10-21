"""Session-tinted two-row toolbar, keeping terminal viewport unobstructed."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from .sidebar import button


class HeaderBar(QWidget):
    restartRequested = pyqtSignal()
    ctrlCRequested = pyqtSignal()
    killPortRequested = pyqtSignal()
    clearRequested = pyqtSignal()
    searchRequested = pyqtSignal(str)
    modeChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workspaceHeader")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(9)
        top = QHBoxLayout()
        self.title = QLabel("Your local development workspace")
        self.title.setObjectName("workspaceTitle")
        top.addWidget(self.title, 1)
        self.mode = QComboBox()
        self.mode.addItem("Sidebar view", "sidebar")
        self.mode.addItem("Top tabs view", "tabs")
        self.mode.setAccessibleName("Session navigation layout")
        self.mode.currentIndexChanged.connect(lambda: self.modeChanged.emit(self.mode.currentData()))
        top.addWidget(self.mode)
        root.addLayout(top)
        bottom = QHBoxLayout()
        self.cwd_label = QLabel("Create a terminal or run a saved workspace")
        self.cwd_label.setObjectName("muted")
        self.cwd_label.setMinimumWidth(60)
        bottom.addWidget(self.cwd_label, 1)
        self.child_label = QLabel()
        self.child_label.setObjectName("muted")
        bottom.addWidget(self.child_label)
        self.restart_btn = button("Restart", "restart", self.restartRequested.emit)
        self.ctrlc_btn = button("Interrupt", "stop", self.ctrlCRequested.emit)
        self.kill_btn = button("Kill listener", "stop", self.killPortRequested.emit)
        self.kill_btn.setObjectName("danger")
        self.clear_btn = button("Clear", "terminal", self.clearRequested.emit)
        for control in (self.restart_btn, self.ctrlc_btn, self.kill_btn, self.clear_btn):
            bottom.addWidget(control)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search terminal…")
        self.search_edit.setMaximumWidth(170)
        self.search_edit.returnPressed.connect(lambda: self.searchRequested.emit(self.search_edit.text()))
        bottom.addWidget(self.search_edit)
        root.addLayout(bottom)
        self.set_session(None)

    def set_session(self, session):
        for control in (self.restart_btn, self.ctrlc_btn, self.kill_btn, self.clear_btn):
            control.setEnabled(session is not None)
        if session is None:
            self.title.setText("Your local development workspace")
            self.cwd_label.setText("Create a terminal or run a saved workspace")
            self.child_label.clear()
            return
        self.title.setText(session.name)
        folder = session.current_cwd or session.cwd or "shell home"
        prefix = "Folder" if session.current_cwd else "Starting folder"
        self.cwd_label.setText(f"{prefix}: {folder}")
        self.cwd_label.setToolTip(folder)
        self.child_label.setText(f"{session.state} · {len({l.port for l in session.listeners})} ports")
        self.child_label.setToolTip("\n".join(str(p) for p in session.children))
        self.restart_btn.setEnabled(session.can_restart())
        self.restart_btn.setToolTip(session.restart_reason() or f"Re-run saved command: {session.restart_cmd}")
        self.kill_btn.setEnabled(bool(session.listeners))
        base = QColor("#101a2a")
        accent = QColor(session.accent)
        mixed = QColor(int(base.red() * .85 + accent.red() * .15),
                       int(base.green() * .85 + accent.green() * .15),
                       int(base.blue() * .85 + accent.blue() * .15))
        self.setStyleSheet(f"QWidget#workspaceHeader{{background:{mixed.name()};border-bottom:1px solid #2b3950;}}")

    def set_child(self, name):
        self.child_label.setToolTip(name)
