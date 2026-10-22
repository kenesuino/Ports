"""One renderer for managed and external listeners; actions are child widgets."""
from functools import partial
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
                            QScrollArea, QFrame, QComboBox, QLineEdit, QMenu)
from .icons import icon
from .theme import SPACE_2, TEXT_MUTED
from .widgets import ElidedLabel


def monospace(widget):
    font = QFont('Consolas', 9)
    font.setStyleHint(QFont.StyleHint.Monospace)
    widget.setFont(font)


class PortRow(QWidget):
    openRequested = pyqtSignal(int)
    killRequested = pyqtSignal(object)
    menuRequested = pyqtSignal(int, object)

    def __init__(self, listener, label='', env_tag='', parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        self.name = ElidedLabel(parent=self)
        self.name.setStyleSheet(f"color:{TEXT_MUTED};")
        layout.addWidget(self.name, 1)
        self.tag = ElidedLabel(parent=self)
        self.tag.setMaximumWidth(48)
        layout.addWidget(self.tag)
        self.port = QLabel(self)
        self.port.setFixedWidth(48)
        monospace(self.port)
        self.port.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.port)
        self.actions = QWidget(self)
        self.actions.setFixedWidth(40)
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(0)
        self.open_button = self._action('browser', 'Open listener', lambda: self.openRequested.emit(self.listener.port))
        self.kill_button = self._action('kill', 'Terminate listener process', lambda: self.killRequested.emit(self.listener))
        actions.addWidget(self.open_button)
        actions.addWidget(self.kill_button)
        layout.addWidget(self.actions)
        self.update_listener(listener, label, env_tag)

    def _action(self, glyph, tip, callback):
        button = QPushButton(self.actions)
        button.setObjectName('rowAction')
        button.setIcon(icon(glyph, size=16))
        button.setAccessibleName(tip)
        button.setToolTip(tip)
        button.setFixedSize(20, 24)
        button.clicked.connect(callback)
        return button

    def _detail_text(self):
        owner = self.listener.owner
        return f'{self.listener.address}:{self.listener.port} · {owner.name if owner else "unknown"} · PID {owner.pid if owner else "?"}'

    def update_listener(self, listener, label='', env_tag=''):
        self.listener = listener
        self.port.setText(f':{listener.port}')
        self.tag.setText(env_tag or label)
        self.setAccessibleDescription(self._detail_text())
        self._sync_detail()

    def _set_detail_visible(self, visible):
        self.name.setText(self._detail_text() if visible else self.listener.owner.name if self.listener.owner else 'unknown')

    def _sync_detail(self):
        self._set_detail_visible(self.underMouse() or self.hasFocus())

    def enterEvent(self, event):
        self._set_detail_visible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_detail_visible(self.hasFocus())
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self._set_detail_visible(True)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._set_detail_visible(self.underMouse())
        super().focusOutEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.openRequested.emit(self.listener.port)
        elif event.button() == Qt.MouseButton.RightButton:
            self.menuRequested.emit(self.listener.port, self.mapToGlobal(event.position().toPoint()))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.openRequested.emit(self.listener.port)
        else:
            super().keyPressEvent(event)


class PortsList(QWidget):
    openRequested = pyqtSignal(str, int)
    killRequested = pyqtSignal(object)
    menuRequested = pyqtSignal(object, int, object)
    external_toggled = pyqtSignal(bool)
    ownerRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows, self._headers = {}, {}
        self._external_open = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE_2)
        self.empty = QLabel('No managed listeners in this scope', self)
        self.empty.setWordWrap(True)
        self.empty.setObjectName('muted')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty)
        self.hint = QLabel('Start a terminal server to detect ports.', self)
        self.hint.setWordWrap(True)
        self.hint.setObjectName('emptyBody')
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.hint)
        self.rows_host = QWidget(self)
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(2)
        root.addWidget(self.rows_host)
        root.addStretch()
        self.external_group = QPushButton('External (0)', self.rows_host)
        self.external_group.setObjectName('groupHeader')
        self.external_group.clicked.connect(lambda: self.external_toggled.emit(not self._external_open))

    def update_rows(self, sessions, labels, external=(), external_open=False):
        wanted, ordered = {}, []
        session_ids = {s.id for s in sessions if s.listeners}
        for sid in list(self._headers):
            if sid not in session_ids:
                self._headers.pop(sid).deleteLater()
        for session in sessions:
            if not session.listeners:
                continue
            if session.id not in self._headers:
                header = QPushButton(self.rows_host)
                header.setObjectName('ownerHeader')
                header.clicked.connect(partial(self.ownerRequested.emit, session.id))
                self._headers[session.id] = header
            header = self._headers[session.id]
            header.setText(session.name)
            header.setToolTip('Focus owning terminal')
            ordered.append(header)
            for listener in session.listeners:
                key = ('session', session.id, listener.address, listener.port, listener.owner.key() if listener.owner else None)
                wanted[key] = (session, listener, labels.get((session.id, listener.port), ''), '')
                ordered.append(key)
        ordered.append(self.external_group)
        for listener in external:
            key = ('external', listener.env, listener.distro, listener.address, listener.port, listener.owner.key() if listener.owner else None)
            wanted[key] = (None, listener, '', 'wsl' if listener.env == 'wsl' else 'win')
            ordered.append(key)
        for key in list(self._rows):
            if key not in wanted:
                widget = self._rows.pop(key)
                self.rows_layout.removeWidget(widget)
                widget.hide()
                widget.deleteLater()
        for key, (session, listener, label, tag) in wanted.items():
            if key not in self._rows:
                row = PortRow(listener, label, tag, self.rows_host)
                row.openRequested.connect(partial(self.openRequested.emit, session.id if session else ''))
                row.killRequested.connect(self.killRequested)
                row.menuRequested.connect(lambda port, point, s=session: self.menuRequested.emit(s, port, point))
                self._rows[key] = row
            self._rows[key].update_listener(listener, label, tag)
        for index, entry in enumerate(ordered):
            widget = self._rows[entry] if isinstance(entry, tuple) else entry
            if self.rows_layout.indexOf(widget) != index:
                self.rows_layout.insertWidget(index, widget)
        self._external_count = len(external)
        self.external_group.setVisible(bool(external))
        self.set_external_open(external_open)
        self.empty.setVisible(not session_ids)
        self.hint.setVisible(not session_ids)

    def set_external_open(self, open_):
        self._external_open = bool(open_)
        for key, row in self._rows.items():
            if key[0] == 'external':
                row.setVisible(self._external_open)
        self.external_group.setText(f'External ({getattr(self, "_external_count", 0)})  {"▾" if open_ else "▸"}')


class PortsInspector(QWidget):
    findPort = pyqtSignal(int)
    openUrl = pyqtSignal(str, int)
    copyUrl = pyqtSignal(str, int)
    killRequested = pyqtSignal(object)
    labelEditRequested = pyqtSignal(str, int)
    probeToggled = pyqtSignal(str, int, bool)
    externalStateChanged = pyqtSignal(bool)
    scopeChanged = pyqtSignal(str)
    ownerRequested = pyqtSignal(str)
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(420)
        self.setObjectName('portsInspector')
        self._listener_cache, self._external = {}, []
        self.external_open = False
        self.probe_enabled = set()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 8)
        title = QHBoxLayout()
        title.addWidget(QLabel('Listening ports'), 1)
        close = QPushButton(self)
        close.setObjectName('iconBtn'); close.setIcon(icon('close'))
        close.setToolTip('Hide ports inspector (Ctrl+Shift+E)')
        close.setAccessibleName('Hide ports inspector')
        close.clicked.connect(lambda: self.visibilityChanged.emit(False))
        title.addWidget(close)
        root.addLayout(title)
        self.scope = QComboBox()
        self.scope.addItem('Selected workspace', 'selected')
        self.scope.addItem('All workspaces', 'all')
        self.scope.currentIndexChanged.connect(lambda: self.scopeChanged.emit(self.scope.currentData()))
        root.addWidget(self.scope)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText('Find port across the machine…')
        self.find_edit.setAccessibleName('Find port globally')
        self.find_edit.returnPressed.connect(self.find)
        root.addWidget(self.find_edit)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.ports_list = PortsList()
        self.ports_list.openRequested.connect(self.openUrl)
        self.ports_list.killRequested.connect(self.killRequested)
        self.ports_list.menuRequested.connect(self.badge_menu)
        self.ports_list.ownerRequested.connect(self.ownerRequested)
        self.ports_list.external_toggled.connect(self._toggle_external)
        self.scroll.setWidget(self.ports_list)
        root.addWidget(self.scroll, 1)

    def find(self):
        text = self.find_edit.text().strip()
        if text.isascii() and text.isdigit() and 1 <= int(text) <= 65535:
            self.findPort.emit(int(text))
        else:
            self.find_edit.setToolTip('Enter port 1–65535')

    def set_listeners(self, sid, listeners):
        self._listener_cache[sid] = listeners

    def update_external(self, listeners):
        self._external = list(listeners)

    def external_listeners(self):
        return self._external

    def update_ports(self, sessions, labels, external=()):
        self.ports_list.update_rows(sessions, labels, external, self.external_open)

    def _toggle_external(self, open_):
        self.external_open = open_
        self.ports_list.set_external_open(open_)
        self.externalStateChanged.emit(open_)

    def badge_menu(self, session, port, point):
        sid = session.id if session else ''
        menu = QMenu(self)
        menu.addAction('Open in browser', lambda: self.openUrl.emit(sid, port))
        menu.addAction('Copy URL', lambda: self.copyUrl.emit(sid, port))
        if session:
            menu.addAction('Edit label…', lambda: self.labelEditRequested.emit(sid, port))
            probe = menu.addAction('Check HTTP response')
            probe.setCheckable(True); probe.setChecked((sid, port) in self.probe_enabled)
            probe.toggled.connect(lambda on: self.probeToggled.emit(sid, port, on))
        listeners = self._listener_cache.get(sid, []) if sid else self._external
        for listener in listeners:
            if listener.port == port:
                action = menu.addAction(f'Terminate {listener.owner.name if listener.owner else "unknown"} ({listener.address})')
                action.triggered.connect(lambda _=False, l=listener: self.killRequested.emit(l))
        menu.exec(point)
