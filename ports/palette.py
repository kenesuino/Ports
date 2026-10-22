"""Ctrl+K command palette: one field, a short list of existing actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)

from .theme import PANEL, SPACE_2, SPACE_3


@dataclass
class PaletteAction:
    title: str
    detail: str
    callback: Callable[[], None]


class CommandPalette(QDialog):
    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.window = window
        self._chosen: PaletteAction | None = None
        self.setWindowTitle("Command palette")
        self.setModal(True)
        self.resize(520, 340)
        self.setStyleSheet(f"QDialog {{ background:{PANEL}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        self.field = QLineEdit()
        self.field.setPlaceholderText(
            "Type an action: new terminal, load workspace, find port…")
        self.field.setAccessibleName("Command palette filter")
        self.field.textChanged.connect(self._filter)
        self.field.returnPressed.connect(self._accept_current)
        layout.addWidget(self.field)

        self.list = QListWidget()
        self.list.setAccessibleName("Matching actions")
        self.list.itemActivated.connect(lambda _: self._accept_current())
        self.list.itemClicked.connect(lambda _: self._accept_current())
        layout.addWidget(self.list)

        self.actions = self._collect()
        self._filter("")
        self.field.setFocus()

    def _collect(self) -> list[PaletteAction]:
        window = self.window
        actions = [
            PaletteAction("New terminal", "Spawn a shell in a chosen folder",
                          window.sidebar.new_terminal),
            PaletteAction("Load workspace", "Remember definitions without starting commands",
                          window.sidebar.load_selected),
            PaletteAction("Save current workspace", "Store open terminals as a profile",
                          lambda: window.profile_action("save", "")),
            PaletteAction("Find port", "Focus the port search field",
                          lambda: (window._panel_visibility_changed(True), window.inspector.find_edit.setFocus())),
            PaletteAction("Preferences", "External filters and motion",
                          window.settings),
            PaletteAction("Keyboard shortcuts", "Show the shortcut sheet",
                          window.show_shortcuts),
            PaletteAction("Toggle ports inspector", "Show or hide the right ports inspector",
                          window.toggle_workspace_panel),
            PaletteAction("Close terminal", "Close the active terminal",
                          lambda: window.close_session(window.manager.active)),
        ]
        for index, session in enumerate(window.visible_sessions()[:9], start=1):
            actions.append(PaletteAction(
                f"Go to {session.name}",
                f"Ctrl+{index} · {session.shell} · {session.state}",
                lambda s=session: window.focus_session(s)))
        return actions

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        self.list.clear()
        for action in self.actions:
            haystack = f"{action.title} {action.detail}".lower()
            if needle and needle not in haystack:
                continue
            item = QListWidgetItem(f"{action.title}    {action.detail}")
            item.setData(Qt.ItemDataRole.UserRole, action)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self._chosen = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def invoke(self) -> None:
        if self._chosen is not None:
            self._chosen.callback()
