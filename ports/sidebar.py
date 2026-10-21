"""Workspace/profile launcher and keyed session/port navigation."""
from functools import partial

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                            QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                            QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .icons import icon
from .motion import HoverButton, expand
from .pty_session import SHELLS, available_shells


def button(text, glyph, callback=None):
    result = HoverButton(text)
    result.setIcon(icon(glyph))
    result.setAccessibleName(text)
    if callback:
        result.clicked.connect(callback)
    return result


class NewSessionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New terminal")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.shell = QComboBox()
        for key in available_shells():
            self.shell.addItem(SHELLS[key]["label"], key)
        form.addRow("Shell", self.shell)
        self.name = QLineEdit()
        form.addRow("Name", self.name)
        self.cwd = QLineEdit()
        folder = QHBoxLayout()
        folder.addWidget(self.cwd)
        browse = button("Browse", "folder", self.browse)
        folder.addWidget(browse)
        form.addRow("Starting folder", folder)
        self.command = QLineEdit()
        self.command.setPlaceholderText("Optional explicit startup / restart command")
        form.addRow("Command", self.command)
        self.distro = QLineEdit()
        self.distro.setPlaceholderText("Default WSL distro, or installed distribution name")
        form.addRow("WSL distribution", self.distro)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self):
        if self.shell.currentData() == "wsl":
            self.cwd.setPlaceholderText("Enter Linux path, e.g. /home/user/project")
            return
        path = QFileDialog.getExistingDirectory(self, "Starting folder")
        if path:
            self.cwd.setText(path)

    def values(self):
        return dict(shell=self.shell.currentData(), cwd=self.cwd.text().strip(),
                    name=self.name.text().strip(), startup_cmd=self.command.text().strip(),
                    distro=self.distro.text().strip())


class SessionCard(QFrame):
    selected = pyqtSignal(object)
    def __init__(self, session, sidebar):
        super().__init__()
        self.session, self.sidebar = session, sidebar
        self.setObjectName("sessionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        top.addWidget(self.title, 1)
        self.close_button = button("", "close", lambda: sidebar.sessionCloseRequested.emit(session))
        self.close_button.setAccessibleName("Close terminal")
        self.close_button.setFixedSize(26, 26)
        top.addWidget(self.close_button)
        layout.addLayout(top)
        self.detail = QLabel()
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.badge_row = QHBoxLayout()
        self.badge_row.setSpacing(5)
        self.badge_row.addStretch()
        layout.addLayout(self.badge_row)
        self.badges = {}
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menu)
        self.refresh()

    def refresh(self):
        session = self.session
        self.title.setText(session.name)
        self.title.setToolTip(session.name)
        child = session.child_name or session.state
        self.detail.setText(f"{SHELLS[session.shell]['label']} · {child}")
        if session.last_error:
            self.detail.setText(f"{session.state}: {session.last_error}")
        self.setAccessibleName(f"{session.name}, {session.state}")

    def set_active(self, active):
        color = self.session.accent if active else "#243044"
        self.setStyleSheet(f"QFrame#sessionCard{{border:1px solid {color};border-radius:7px;background:#111a28;}}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.session)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.selected.emit(self.session)
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.sidebar.renameRequested.emit(self.session.id)

    def menu(self, point):
        menu = QMenu(self)
        menu.addAction(icon("edit"), "Rename", lambda: self.sidebar.renameRequested.emit(self.session.id))
        menu.addAction(icon("retry"), "Retry failed launch", lambda: self.sidebar.retryRequested.emit(self.session.id)).setEnabled(self.session.state in ("failed", "exited"))
        menu.addAction("Move up", lambda: self.sidebar.moveRequested.emit(self.session.id, -1))
        menu.addAction("Move down", lambda: self.sidebar.moveRequested.emit(self.session.id, 1))
        menu.addAction(icon("close"), "Close", lambda: self.sidebar.sessionCloseRequested.emit(self.session))
        menu.exec(self.mapToGlobal(point))

    def ports(self, listeners, labels, health):
        keyed = {}
        for listener in listeners:
            keyed.setdefault(listener.port, []).append(listener)
        # Keep rows stable between polls, including open context menus.
        for port in list(self.badges):
            if port not in keyed:
                self.badges.pop(port).deleteLater()
        for port, owners in keyed.items():
            if port not in self.badges:
                badge = QPushButton()
                badge.setObjectName("portBadge")
                badge.setCursor(Qt.CursorShape.PointingHandCursor)
                badge.clicked.connect(partial(self.sidebar.openUrl.emit, self.session.id, port))
                badge.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                badge.customContextMenuRequested.connect(partial(self.sidebar.badge_menu, self.session, port, badge))
                self.badges[port] = badge
                self.badge_row.insertWidget(self.badge_row.count() - 1, badge)
            badge = self.badges[port]
            label = labels.get(port, "")
            badge.setText(f":{port}" + (f" {label[:12]}" if label else ""))
            detail = "\n".join(f"{l.address}:{l.port} · {l.owner.name if l.owner else 'unknown'}" for l in owners)
            if any(l.is_wildcard for l in owners):
                detail += "\nWildcard binding: potentially LAN reachable (firewall dependent)"
            detail += "\n" + health.get((self.session.id, port), "HTTP unchecked")
            badge.setToolTip(detail)
        if self.session.expected_ports:
            observed = set(keyed)
            missing = sorted(set(self.session.expected_ports) - observed)
            text = "Expected: " + ", ".join(f":{p} {'waiting' if p in missing else 'listening'}" for p in self.session.expected_ports)
            self.detail.setText(self.detail.text() + "\n" + text)
            self.detail.setToolTip(text)


class Sidebar(QWidget):
    newSessionRequested = pyqtSignal(dict)
    sessionSelected = pyqtSignal(object)
    sessionCloseRequested = pyqtSignal(object)
    renameRequested = pyqtSignal(str)
    retryRequested = pyqtSignal(str)
    moveRequested = pyqtSignal(str, int)
    findPort = pyqtSignal(int)
    openUrl = pyqtSignal(str, int)
    copyUrl = pyqtSignal(str, int)
    killRequested = pyqtSignal(object)
    labelEditRequested = pyqtSignal(str, int)
    probeToggled = pyqtSignal(str, int, bool)
    profileAction = pyqtSignal(str, str)
    settingsRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(250)
        self.setMaximumWidth(420)
        self._cards, self._listener_cache, self._external_rows = {}, {}, {}
        self.motion_disabled = False
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)
        brand = QLabel("PORTS")
        brand.setObjectName("brand")
        root.addWidget(brand)
        row = QHBoxLayout()
        caption = QLabel("WORKSPACES")
        caption.setObjectName("sectionLabel")
        row.addWidget(caption, 1)
        manage = button("", "settings", self.profile_menu)
        manage.setAccessibleName("Manage workspace profiles")
        manage.setToolTip("New, edit, duplicate, save or remove workspace profile")
        row.addWidget(manage)
        root.addLayout(row)
        self.profile_combo = QComboBox()
        self.profile_combo.setAccessibleName("Workspace profile")
        root.addWidget(self.profile_combo)
        launch = QHBoxLayout()
        launch.addWidget(button("Run workspace", "run", lambda: self.profileAction.emit("run", self.profile_combo.currentData() or "")), 1)
        menu = button("", "chevron", self.profile_menu)
        menu.setAccessibleName("Workspace actions")
        launch.addWidget(menu)
        root.addLayout(launch)
        root.addWidget(button("New terminal", "add", self.new_terminal))
        row = QHBoxLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find localhost port…")
        self.find_edit.setAccessibleName("Find port")
        self.find_edit.returnPressed.connect(self.find)
        row.addWidget(self.find_edit, 1)
        find = button("", "search", self.find)
        find.setAccessibleName("Find port owners")
        row.addWidget(find)
        root.addLayout(row)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        self.cards_layout = QVBoxLayout(host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()
        self.scroll.setWidget(host)
        root.addWidget(self.scroll, 1)
        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.ext_toggle = button("External listeners", "chevron")
        self.ext_toggle.setCheckable(True)
        self.ext_toggle.toggled.connect(lambda visible: expand(self.ext_panel, visible, self.motion_disabled))
        root.addWidget(self.ext_toggle)
        self.ext_panel = QScrollArea()
        self.ext_panel.setWidgetResizable(True)
        self.ext_panel.setFrameShape(QFrame.Shape.NoFrame)
        self.ext_panel.hide()
        host = QWidget()
        self.ext_layout = QVBoxLayout(host)
        self.ext_layout.setContentsMargins(0, 0, 0, 0)
        self.ext_layout.addStretch()
        self.ext_panel.setWidget(host)
        root.addWidget(self.ext_panel)
        root.addWidget(button("Preferences", "settings", self.settingsRequested.emit))

    def new_terminal(self):
        dialog = NewSessionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.newSessionRequested.emit(dialog.values())

    def find(self):
        text = self.find_edit.text().strip()
        if text.isascii() and text.isdigit() and 1 <= int(text) <= 65535:
            self.find_edit.setStyleSheet("")
            self.findPort.emit(int(text))
        else:
            self.find_edit.setStyleSheet("border:1px solid #f7768e")
            self.find_edit.setToolTip("Enter an integer from 1 to 65535")

    def set_profiles(self, profiles):
        selected = self.profile_combo.currentData()
        self.profile_combo.clear()
        self.profile_combo.addItem("Select workspace…", "")
        for profile in profiles:
            self.profile_combo.addItem(profile.name, profile.id)
        index = self.profile_combo.findData(selected)
        self.profile_combo.setCurrentIndex(max(0, index))

    def profile_menu(self):
        menu = QMenu(self)
        identifier = self.profile_combo.currentData() or ""
        for title, action in [("New profile…", "new"), ("Save current workspace…", "save"),
                               ("Edit profile…", "edit"), ("Duplicate profile…", "duplicate"),
                               ("Launch another copy", "copy"), ("Restore missing terminals", "missing"),
                               ("Delete profile", "delete")]:
            entry = menu.addAction(title, partial(self.profileAction.emit, action, identifier))
            entry.setEnabled(action in ("new", "save") or bool(identifier))
        menu.exec(self.profile_combo.mapToGlobal(self.profile_combo.rect().bottomLeft()))

    def add_session(self, session):
        card = SessionCard(session, self)
        card.selected.connect(self.sessionSelected)
        self._cards[session.id] = card
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def remove_session(self, identifier):
        card = self._cards.pop(identifier, None)
        self._listener_cache.pop(identifier, None)
        if card:
            card.deleteLater()

    def set_active(self, session):
        for card in self._cards.values():
            card.set_active(card.session is session)

    def sync_order(self, sessions):
        for position, session in enumerate(sessions):
            card = self._cards.get(session.id)
            if card:
                self.cards_layout.removeWidget(card)
                self.cards_layout.insertWidget(position, card)

    def set_listeners(self, identifier, listeners):
        self._listener_cache[identifier] = listeners

    def _listeners_for(self, identifier):
        return self._listener_cache.get(identifier, [])

    def update_card(self, session, listeners, labels, health=None):
        card = self._cards.get(session.id)
        if card:
            card.refresh()
            card.ports(listeners, labels, health or {})

    def badge_menu(self, session, port, badge, point):
        menu = QMenu(self)
        menu.addAction(icon("browser"), "Open in browser", partial(self.openUrl.emit, session.id, port))
        menu.addAction(icon("copy"), "Copy URL", partial(self.copyUrl.emit, session.id, port))
        menu.addAction(icon("edit"), "Edit label…", partial(self.labelEditRequested.emit, session.id, port))
        check = menu.addAction("Check HTTP response")
        check.setCheckable(True)
        check.setChecked((session.id, port) in getattr(self, "probe_enabled", set()))
        check.toggled.connect(partial(self.probeToggled.emit, session.id, port))
        menu.addSeparator()
        for listener in self._listeners_for(session.id):
            if listener.port == port:
                name = listener.owner.name if listener.owner else "unknown"
                menu.addAction(icon("stop", "#f7768e"), f"Force kill {name}", partial(self.killRequested.emit, listener))
        menu.exec(badge.mapToGlobal(point))

    def update_external(self, listeners):
        keyed = {(l.env, l.distro, l.address, l.port, l.owner.key() if l.owner else None): l for l in listeners}
        for key in list(self._external_rows):
            if key not in keyed:
                self._external_rows.pop(key).deleteLater()
        for key, listener in keyed.items():
            if key in self._external_rows:
                continue
            holder = QWidget()
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 2, 0, 2)
            name = listener.owner.name if listener.owner else "unknown"
            label = QLabel(f":{listener.port}  {name}")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setToolTip(f"{listener.env} {listener.distro} {listener.address}")
            row.addWidget(label, 1)
            open_button = button("", "browser", partial(self.openUrl.emit, "", listener.port))
            open_button.setToolTip("Open listener")
            row.addWidget(open_button)
            kill_button = button("", "stop", partial(self.killRequested.emit, listener))
            kill_button.setToolTip("Force kill listener owner")
            row.addWidget(kill_button)
            self.ext_layout.insertWidget(self.ext_layout.count() - 1, holder)
            self._external_rows[key] = holder
        self.ext_toggle.setText(f"External listeners ({len(keyed)})")
