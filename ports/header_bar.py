"""Header bar: active session folder, child process, port chips, actions."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget


class HeaderBar(QWidget):
    restartRequested = pyqtSignal()
    ctrlCRequested = pyqtSignal()
    killPortRequested = pyqtSignal()
    clearRequested = pyqtSignal()
    searchRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.cwd_label = QLabel("No session")
        self.cwd_label.setObjectName("mono")
        layout.addWidget(self.cwd_label, 1)

        self.child_label = QLabel("")
        self.child_label.setObjectName("muted")
        layout.addWidget(self.child_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search buffer...")
        self.search_edit.setFixedWidth(160)
        self.search_edit.returnPressed.connect(
            lambda: self.searchRequested.emit(self.search_edit.text()))
        layout.addWidget(self.search_edit)

        self.restart_btn = QPushButton("Restart")
        self.restart_btn.clicked.connect(self.restartRequested)
        self.ctrlc_btn = QPushButton("Ctrl+C")
        self.ctrlc_btn.clicked.connect(self.ctrlCRequested)
        self.kill_btn = QPushButton("Kill Port Process")
        self.kill_btn.setObjectName("danger")
        self.kill_btn.clicked.connect(self.killPortRequested)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clearRequested)
        for b in (self.restart_btn, self.ctrlc_btn, self.kill_btn,
                  self.clear_btn):
            layout.addWidget(b)

    def set_session(self, session) -> None:
        if session is None:
            self.cwd_label.setText("No session")
            self.child_label.setText("")
            for b in (self.restart_btn, self.ctrlc_btn, self.kill_btn,
                      self.clear_btn):
                b.setEnabled(False)
            return
        folder = session.cwd or "(shell home)"
        self.cwd_label.setText(folder)
        for b in (self.ctrlc_btn, self.clear_btn):
            b.setEnabled(True)
        can = session.can_restart()
        self.restart_btn.setEnabled(can)
        self.restart_btn.setToolTip(session.restart_reason()
                                    or f"Re-run: {session.restart_cmd}")
        self.kill_btn.setEnabled(True)

    def set_child(self, name: str) -> None:
        self.child_label.setText(name)
