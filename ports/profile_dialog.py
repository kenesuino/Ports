"""Qt-native workspace editor; edits detached profile copies."""
from copy import deepcopy

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                            QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                            QListWidget, QMessageBox, QPushButton, QSplitter,
                            QVBoxLayout, QWidget)

from .profiles import TerminalProfile, WorkspaceProfile
from .pty_session import SHELLS, available_shells

COLORS = ["#7aa2f7", "#7dcfff", "#9ece6a", "#bb9af7", "#e0af68", "#f7768e"]


class ProfileDialog(QDialog):
    def __init__(self, profile=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Workspace profile")
        self.resize(840, 570)
        self.profile = deepcopy(profile) if profile else WorkspaceProfile(name="New workspace", terminals=[TerminalProfile(name="Terminal 1")])
        self._index = -1
        layout = QVBoxLayout(self)
        self.name = QLineEdit(self.profile.name)
        self.name.setPlaceholderText("Workspace name")
        layout.addWidget(self.name)
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.items = QListWidget()
        left_layout.addWidget(self.items)
        buttons = QHBoxLayout()
        for text, action in [("Add", self.add), ("Remove", self.remove), ("↑", lambda: self.move(-1)), ("↓", lambda: self.move(1))]:
            button = QPushButton(text)
            button.clicked.connect(action)
            buttons.addWidget(button)
        left_layout.addLayout(buttons)
        splitter.addWidget(left)
        right = QWidget()
        form = QFormLayout(right)
        self.fields = {}
        for key, title in [("name", "Terminal name"), ("cwd", "Starting folder"),
                           ("startup_cmd", "Startup command"), ("restart_cmd", "Restart command"),
                           ("distro", "WSL distribution"), ("expected_ports", "Expected ports")]:
            edit = QLineEdit()
            self.fields[key] = edit
            if key == "cwd":
                row = QHBoxLayout()
                row.addWidget(edit)
                browse = QPushButton("Browse")
                browse.clicked.connect(self.browse)
                row.addWidget(browse)
                form.addRow(title, row)
            else:
                form.addRow(title, edit)
        self.fields["expected_ports"].setPlaceholderText("3000, 8000 (optional)")
        self.shell = QComboBox()
        discovered = available_shells()
        for key, spec in SHELLS.items():
            self.shell.addItem(spec["label"] + (" (unavailable)" if key not in discovered else ""), key)
        form.insertRow(1, "Shell", self.shell)
        self.accent = QComboBox()
        for color in COLORS:
            self.accent.addItem(color, color)
        form.addRow("Accent", self.accent)
        note = QLabel("Commands run only through explicit Run. First run and executable edits require review. Linux folders are validated inside WSL. Avoid storing secrets in commands.")
        note.setWordWrap(True)
        form.addRow(note)
        splitter.addWidget(right)
        splitter.setSizes([220, 560])
        layout.addWidget(splitter)
        self.items.currentRowChanged.connect(self.select)
        self.refresh(0)
        footer = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        footer.accepted.connect(self.accept)
        footer.rejected.connect(self.reject)
        layout.addWidget(footer)

    def store(self):
        if not 0 <= self._index < len(self.profile.terminals):
            return
        terminal = self.profile.terminals[self._index]
        for key, edit in self.fields.items():
            if key == "expected_ports":
                parts = [p.strip() for p in edit.text().split(",") if p.strip()]
                if any(not p.isdigit() or not 1 <= int(p) <= 65535 for p in parts):
                    raise ValueError("Expected ports must be integers from 1 to 65535")
                terminal.expected_ports = list(dict.fromkeys(int(p) for p in parts))
            else:
                setattr(terminal, key, edit.text().strip())
        terminal.shell = self.shell.currentData()
        terminal.accent = self.accent.currentData()
        if not terminal.name:
            raise ValueError("Every terminal needs a name")

    def select(self, index):
        try:
            self.store()
        except ValueError as exc:
            QMessageBox.warning(self, "Profile", str(exc))
        self._index = index
        if not 0 <= index < len(self.profile.terminals):
            return
        terminal = self.profile.terminals[index]
        for key, edit in self.fields.items():
            value = getattr(terminal, key)
            edit.setText(", ".join(map(str, value)) if key == "expected_ports" else value)
        self.shell.setCurrentIndex(max(0, self.shell.findData(terminal.shell)))
        self.accent.setCurrentIndex(max(0, self.accent.findData(terminal.accent)))

    def refresh(self, index):
        self.items.blockSignals(True)
        self.items.clear()
        self.items.addItems([t.name for t in self.profile.terminals])
        self._index = -1
        self.items.setCurrentRow(index)
        self.items.blockSignals(False)
        self.select(index)

    def add(self):
        try:
            self.store()
        except ValueError as exc:
            QMessageBox.warning(self, "Profile", str(exc)); return
        self.profile.terminals.append(TerminalProfile(name=f"Terminal {len(self.profile.terminals) + 1}"))
        self.refresh(len(self.profile.terminals) - 1)

    def remove(self):
        if len(self.profile.terminals) <= 1:
            return
        index = max(0, self.items.currentRow())
        self.profile.terminals.pop(index)
        self.refresh(min(index, len(self.profile.terminals) - 1))

    def move(self, offset):
        try:
            self.store()
        except ValueError:
            return
        index = self.items.currentRow()
        other = index + offset
        if 0 <= other < len(self.profile.terminals):
            self.profile.terminals[index], self.profile.terminals[other] = self.profile.terminals[other], self.profile.terminals[index]
            self.refresh(other)

    def browse(self):
        if self.shell.currentData() == "wsl":
            QMessageBox.information(self, "Linux folder", "Enter the Linux path, for example /home/user/project.")
            return
        path = QFileDialog.getExistingDirectory(self, "Starting folder")
        if path:
            self.fields["cwd"].setText(path)

    def accept(self):
        try:
            self.store()
            self.profile.name = self.name.text().strip()
            if not self.profile.name:
                raise ValueError("Workspace needs a name")
            # Revalidate using the same trust-boundary rules as config load.
            self.profile = WorkspaceProfile.from_dict(self.profile.to_dict())
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Profile", str(exc)); return
        super().accept()
