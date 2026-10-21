"""Left command sidebar: launcher, find/kill bar, session cards, external ports."""

from __future__ import annotations

from functools import partial

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .pty_session import SHELLS, available_shells


class NewSessionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Terminal")
        self.shells = available_shells()
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.shell_combo = QComboBox()
        for key in self.shells:
            self.shell_combo.addItem(SHELLS[key]["label"], key)
        form.addRow("Shell", self.shell_combo)

        row = QHBoxLayout()
        self.cwd_edit = QLineEdit()
        self.cwd_edit.setPlaceholderText("Starting folder (optional)")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        row.addWidget(self.cwd_edit, 1)
        row.addWidget(browse)
        form.addRow("Folder", row)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name (optional)")
        form.addRow("Name", self.name_edit)

        self.startup_edit = QLineEdit()
        self.startup_edit.setPlaceholderText("e.g. npm run dev (also used by Restart)")
        form.addRow("Startup command", self.startup_edit)

        self.distro_edit = QLineEdit("Ubuntu")
        self.distro_edit.setPlaceholderText("WSL distribution")
        self.distro_row = form.rowCount()
        form.addRow("Distro", self.distro_edit)
        self.shell_combo.currentIndexChanged.connect(self._toggle_distro)
        self._toggle_distro()

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Starting folder")
        if path:
            self.cwd_edit.setText(path)

    def _toggle_distro(self):
        is_wsl = self.shell_combo.currentData() == "wsl"
        self.distro_edit.setVisible(is_wsl)
        self.distro_edit.setEnabled(is_wsl)

    def values(self) -> dict:
        return {
            "shell": self.shell_combo.currentData(),
            "cwd": self.cwd_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "startup_cmd": self.startup_edit.text().strip(),
            "distro": self.distro_edit.text().strip(),
        }


class PortBadge(QPushButton):
    """Clickable :PORT chip; click opens browser, right-click opens menu."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(22)
        self.setStyleSheet(
            "QPushButton { background:#12321f; border:1px solid #1f5138;"
            " color:#7ee2a8; border-radius:11px; padding:0 10px;"
            " font-family:'Cascadia Code',Consolas,monospace; font-size:12px;}"
            "QPushButton:hover { background:#1a4530; }")

    def set_health(self, color: str) -> None:
        style = self.styleSheet()
        self.setStyleSheet(style.replace("color:#7ee2a8", f"color:{color}"))


class SessionCard(QFrame):
    clicked = pyqtSignal(object)
    closed = pyqtSignal(object)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self.title = QLabel(f"<b>{session.name}</b>")
        shell_label = SHELLS.get(session.shell, {}).get("label", session.shell)
        if session.shell == "wsl" and session.distro:
            shell_label = f"WSL: {session.distro}"
        self.sub = QLabel(shell_label)
        self.sub.setObjectName("muted")
        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setObjectName("danger")
        close_btn.clicked.connect(lambda: self.closed.emit(self.session))
        top.addWidget(self.title, 1)
        top.addWidget(close_btn)
        layout.addLayout(top)
        layout.addWidget(self.sub)

        self.child = QLabel("")
        self.child.setObjectName("muted")
        layout.addWidget(self.child)

        self.badges = QHBoxLayout()
        self.badges.setSpacing(6)
        self.badges.addStretch(1)
        layout.addLayout(self.badges)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.session)
        super().mousePressEvent(event)

    def clear_badges(self) -> None:
        while self.badges.count() > 1:
            item = self.badges.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class Sidebar(QWidget):
    newSessionRequested = pyqtSignal(dict)
    sessionSelected = pyqtSignal(object)
    sessionCloseRequested = pyqtSignal(object)
    findPort = pyqtSignal(int)
    openUrl = pyqtSignal(str, int)          # env key, port
    killRequested = pyqtSignal(object)      # Listener
    labelEditRequested = pyqtSignal(str, int)  # scope, port
    probeToggled = pyqtSignal(str, int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(420)
        self._cards: dict[str, SessionCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("<b>PORTS</b>")
        title.setStyleSheet("font-size:16px; letter-spacing:3px;")
        root.addWidget(title)

        new_btn = QPushButton("+ New Terminal")
        new_btn.clicked.connect(self._new_session)
        root.addWidget(new_btn)

        find_row = QHBoxLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find port...")
        self.find_edit.returnPressed.connect(self._find)
        find_btn = QPushButton("Find")
        find_btn.clicked.connect(self._find)
        find_row.addWidget(self.find_edit, 1)
        find_row.addWidget(find_btn)
        root.addLayout(find_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.cards_host)
        root.addWidget(self.scroll, 1)

        # External ports panel (collapsible)
        self.ext_toggle = QPushButton("External ports  ▸")
        self.ext_toggle.setCheckable(True)
        self.ext_toggle.toggled.connect(self._toggle_external)
        root.addWidget(self.ext_toggle)
        self.ext_panel = QScrollArea()
        self.ext_panel.setWidgetResizable(True)
        self.ext_panel.setFrameShape(QFrame.Shape.NoFrame)
        self.ext_panel.setMaximumHeight(220)
        self.ext_panel.setVisible(False)
        self.ext_host = QWidget()
        self.ext_layout = QVBoxLayout(self.ext_host)
        self.ext_layout.setContentsMargins(0, 0, 0, 0)
        self.ext_layout.setSpacing(4)
        self.ext_layout.addStretch(1)
        self.ext_panel.setWidget(self.ext_host)
        root.addWidget(self.ext_panel)

    # -- launcher -------------------------------------------------------

    def _new_session(self):
        dlg = NewSessionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.newSessionRequested.emit(dlg.values())

    def _find(self):
        text = self.find_edit.text().strip()
        if text.isdigit() and 1 <= int(text) <= 65535:
            self.findPort.emit(int(text))

    def _toggle_external(self, on: bool):
        self.ext_panel.setVisible(on)
        self.ext_toggle.setText("External ports  ▾" if on
                                else "External ports  ▸")

    # -- session cards ----------------------------------------------------

    def add_session(self, session) -> None:
        card = SessionCard(session)
        card.clicked.connect(self.sessionSelected)
        card.closed.connect(self.sessionCloseRequested)
        self._cards[session.id] = card
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def remove_session(self, session_id: str) -> None:
        card = self._cards.pop(session_id, None)
        if card:
            card.deleteLater()

    def set_active(self, session) -> None:
        for sid, card in self._cards.items():
            card.set_active(session is not None and sid == session.id)

    def update_card(self, session, listeners, labels: dict) -> None:
        card = self._cards.get(session.id)
        if not card:
            return
        child = session.active_child_name()
        card.child.setText(child or "idle")
        card.clear_badges()
        seen = set()
        for l in listeners:
            if l.port in seen:
                continue
            seen.add(l.port)
            label = labels.get((session.id, l.port), "")
            text = f":{l.port}" + (f" {label}" if label else "")
            badge = PortBadge(text)
            if l.is_wildcard:
                badge.setToolTip(f"{l.address}:{l.port} - LAN-reachable")
            badge.clicked.connect(
                partial(self.openUrl.emit, session.id, l.port))
            badge.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            badge.customContextMenuRequested.connect(
                partial(self._badge_menu, session, l.port))
            card.badges.insertWidget(card.badges.count() - 1, badge)

    def _badge_menu(self, session, port: int, pos) -> None:
        card = self._cards.get(session.id)
        if not card:
            return
        menu = QMenu(self)
        menu.addAction("Open in browser",
                       partial(self.openUrl.emit, session.id, port))
        menu.addAction("Edit label...",
                       partial(self.labelEditRequested.emit, session.id, port))
        menu.addSeparator()
        for l in self._listeners_for(session.id):
            if l.port != port:
                continue
            menu.addAction(
                f"Kill {l.owner.name if l.owner else '?'} (PID "
                f"{l.owner.pid if l.owner else '?'})",
                partial(self.killRequested.emit, l))
        menu.exec(card.mapToGlobal(pos))

    _listener_cache: dict = {}

    def set_listeners(self, session_id: str, listeners) -> None:
        self._listener_cache[session_id] = listeners

    def _listeners_for(self, session_id: str):
        return self._listener_cache.get(session_id, [])

    # -- external panel ---------------------------------------------------

    def update_external(self, listeners) -> None:
        while self.ext_layout.count() > 1:
            item = self.ext_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for l in listeners[:50]:
            row = QHBoxLayout()
            name = l.owner.name if l.owner else "unknown"
            pid = l.owner.pid if l.owner else "?"
            env = "wsl" if l.env == "wsl" else "win"
            text = QLabel(f":{l.port}  {name} ({pid}) [{env}]")
            text.setObjectName("mono")
            open_btn = QPushButton("Open")
            open_btn.setFixedWidth(52)
            open_btn.clicked.connect(partial(self.openUrl.emit, "", l.port))
            kill_btn = QPushButton("Kill")
            kill_btn.setFixedWidth(44)
            kill_btn.setObjectName("danger")
            kill_btn.clicked.connect(partial(self.killRequested.emit, l))
            row.addWidget(text, 1)
            row.addWidget(open_btn)
            row.addWidget(kill_btn)
            holder = QWidget()
            holder.setLayout(row)
            self.ext_layout.insertWidget(self.ext_layout.count() - 1, holder)
