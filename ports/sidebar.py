"""Always-expanded workspace tree. Loading/unpinning never controls processes."""
from PyQt6.QtCore import QEvent, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor, QFont, QIcon, QPainter, QPen
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QComboBox, QMenu, QStyle, QTreeWidget, QTreeWidgetItem,
                            QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QFileDialog)
from .icons import icon, brand_mark
from .motion import HoverButton
from .pty_session import SHELLS, available_shells
from .theme import BORDER, HOVER
from .workspace_navigation import OTHER, format_duration, derive_rows
from .tree_actions import TerminalRowActions
from .tree_delegate import TreeDelegate
# Compatibility imports retain one renderer, not a second implementation.
from .ports_inspector import PortRow, PortsList, monospace


def button(text, glyph, callback=None, style=''):
    widget = HoverButton(text)
    widget.setIcon(icon(glyph))
    widget.setAccessibleName(text)
    if style:
        widget.setObjectName(style)
    if callback: widget.clicked.connect(callback)
    return widget


class NewSessionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('New terminal')
        root = QVBoxLayout(self); form = QFormLayout()
        self.shell = QComboBox()
        for key in available_shells(): self.shell.addItem(SHELLS[key]['label'], key)
        self.name, self.cwd, self.command, self.distro = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        for title, widget in [('Name', self.name), ('Shell', self.shell), ('Starting folder', self.cwd), ('Startup command', self.command), ('WSL distribution', self.distro)]:
            form.addRow(title, widget)
        browse = QPushButton('Browse Windows folder')
        browse.clicked.connect(self.browse); form.addRow(browse)
        root.addLayout(form)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.accept); controls.rejected.connect(self.reject)
        root.addWidget(controls)

    def browse(self):
        if self.shell.currentData() != 'wsl':
            path = QFileDialog.getExistingDirectory(self, 'Starting folder')
            if path: self.cwd.setText(path)

    def values(self):
        return dict(shell=self.shell.currentData(), name=self.name.text().strip(), cwd=self.cwd.text().strip(), startup_cmd=self.command.text().strip(), distro=self.distro.text().strip())


class SidebarTree(QTreeWidget):
    _has_draw_row_bg = True

    def drawRow(self, painter, option, index):
        selected = (self.currentItem() is self.itemFromIndex(index)) or self.selectionModel().isSelected(index)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            bg = QColor(HOVER if selected else '#1b1b1b')
            border = QColor(BORDER if selected else '#202020')
            painter.setPen(QPen(border, 1))
            painter.setBrush(bg)
            row_rect = QRect(4, option.rect.y() + 1, self.viewport().width() - 8, option.rect.height() - 2)
            painter.drawRoundedRect(row_rect, 6, 6)
            painter.restore()
        super().drawRow(painter, option, index)


class Sidebar(QWidget):
    newSessionRequested = pyqtSignal(dict)
    profileAction = pyqtSignal(str, str)
    scopeSelected = pyqtSignal(str)
    terminalSelected = pyqtSignal(object)
    terminalAction = pyqtSignal(str, object)
    workspaceRemoved = pyqtSignal(str)
    expansionChanged = pyqtSignal(list)
    settingsRequested = pyqtSignal()
    shortcutSheetRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('rail')
        self.setMinimumWidth(220); self.setMaximumWidth(420)
        self._items, self._row_data, self._profiles = {}, {}, []
        self._expanded = set()
        root = QVBoxLayout(self); root.setContentsMargins(12, 12, 12, 8); root.setSpacing(8)
        brand = QHBoxLayout()
        self.mark = QLabel(); self.mark.setPixmap(brand_mark(22))
        self.brand = QLabel('Ports'); self.brand.setObjectName('brand')
        brand.addWidget(self.mark); brand.addWidget(self.brand, 1)
        plus = button('', 'add', lambda: self.profileAction.emit('new', ''), 'iconBtn')
        plus.setAccessibleName('New workspace'); plus.setToolTip('New workspace profile')
        brand.addWidget(plus); root.addLayout(brand)
        self.profile_combo = QComboBox()
        self.profile_combo.setAccessibleName('Saved workspace to load')
        self.profile_combo.setToolTip('Pick a saved workspace to show it in this sidebar')
        self.profile_combo.currentIndexChanged.connect(self._combo_activated)
        root.addWidget(self.profile_combo)
        caption = QLabel('Loaded workspaces'); caption.setObjectName('sectionLabel'); root.addWidget(caption)
        self.new_terminal_button = button('New terminal', 'add', self.new_terminal, 'railAction')
        root.addWidget(self.new_terminal_button)
        self.tree = SidebarTree()
        self.tree.setColumnCount(2); self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True); self.tree.setIndentation(16)
        self.tree.setUniformRowHeights(True)
        self.tree.setAccessibleName('Loaded workspaces and terminals')
        self.tree.setColumnWidth(1, 66)
        self.tree.header().setStretchLastSection(False)
        from PyQt6.QtWidgets import QHeaderView
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(1, 66)
        self.tree.itemActivated.connect(lambda item, column: self._clicked(item, column))
        self.tree.itemClicked.connect(self._clicked)
        self.tree.setMouseTracking(True)
        self.tree.viewport().setMouseTracking(True)
        self.tree.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.tree.itemEntered.connect(lambda item, column: self._sync_actions_to_item(item))
        self.tree.viewport().installEventFilter(self)
        self.tree.installEventFilter(self)
        self.row_actions = TerminalRowActions(self.tree.viewport())
        self._actions_item = None
        self.row_actions.triggered.connect(self._row_action)
        self.row_actions.installEventFilter(self)
        for action_button in self.row_actions.buttons.values():
            action_button.installEventFilter(self)
        self.tree.verticalScrollBar().valueChanged.connect(lambda _: self._refresh_row_actions())
        self.tree.horizontalScrollBar().valueChanged.connect(lambda _: self._refresh_row_actions())
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemExpanded.connect(self._expansion)
        self.tree.itemCollapsed.connect(self._expansion)
        self.tree.setItemDelegate(TreeDelegate(self.tree))
        # The tree paints its own per-column selection under the delegate.
        # Suppressing the native indicator leaves the delegate as the only
        # painter of the row, so the band stays continuous.
        self.tree.setStyleSheet(
            'QTreeWidget {background:transparent; border:none; outline:none;}'
            'QTreeWidget::item {height:30px; padding:2px 4px; border:none;'
            ' background:transparent;}'
            'QTreeWidget::item:selected {background:transparent; color:transparent;}'
            'QTreeWidget::item:hover:!selected {background:transparent;}'
            'QTreeWidget::branch {background:transparent;}'
        )
        root.addWidget(self.tree, 1)
        self.manage_button = button('Manage saved profiles', 'settings', lambda: self.profileAction.emit('manage', ''), 'railAction')
        root.addWidget(self.manage_button)
        root.addWidget(button('Preferences', 'settings', self.settingsRequested.emit, 'railAction'))
        self.tree.currentItemChanged.connect(self._current_changed)

    def set_profiles(self, profiles):
        selected = self.profile_combo.currentData()
        self._profiles = list(profiles)
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear(); self.profile_combo.addItem('Choose saved workspace…', '')
        for profile in profiles: self.profile_combo.addItem(profile.name, profile.id)
        self.profile_combo.setCurrentIndex(max(0, self.profile_combo.findData(selected)))
        self.profile_combo.blockSignals(False)

    def _combo_activated(self, index: int) -> None:
        """Choosing a saved workspace loads it; no extra confirm step."""
        identifier = self.profile_combo.itemData(index) if index >= 0 else None
        if identifier:
            self.profileAction.emit('load', identifier)

    def load_selected(self):
        identifier = self.profile_combo.currentData()
        if identifier: self.profileAction.emit('load', identifier)

    def new_terminal(self):
        dialog = NewSessionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.newSessionRequested.emit(dialog.values())

    def sync(self, profiles, navigation, sessions, expanded, active):
        self.tree.blockSignals(True)
        selected_item = self.tree.currentItem()
        selected_key = next((key for key, item in self._items.items() if item is selected_item), None)
        selected_data = selected_item.data(0, Qt.ItemDataRole.UserRole) if selected_item else None
        keep_selection = bool(selected_data and selected_data.get('scope') == navigation.selected)
        wanted, order = set(), []
        profile_map = {p.id: p for p in profiles}
        scopes = [(sid, profile_map[sid]) for sid in navigation.loaded if sid in profile_map] + [(OTHER, None)]
        for scope, profile in scopes:
            group_key = ('workspace', scope)
            title = profile.name if profile else 'Other terminals'
            group = self._item(group_key, None, title)
            group.setData(0, Qt.ItemDataRole.UserRole, {'scope': scope, 'workspace': True})
            group.setFont(0, self._heading_font())
            group.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            group.setIcon(0, icon('workspace', '#b4b4b4', 16) if profile else icon('layout', '#8e8e8e', 16))
            wanted.add(group_key); order.append(group)
            if profile:
                scoped_sessions = [s for s in sessions if s.profile_id == scope]
                rows = derive_rows(profile, scoped_sessions)
            else:
                rows = derive_rows(None, [s for s in sessions if navigation.scope(s) == OTHER])
            rows = list(rows)
            instance_count = len({row['instance_id'] for row in rows if row['instance_id']})
            instances = {}
            for row in rows:
                row = dict(row, scope=scope)
                parent = group
                if instance_count > 1 and row['instance_id']:
                    instance_key = ('instance', scope, row['instance_id'])
                    parent = self._item(instance_key, group, row['group'])
                    parent.setData(0, Qt.ItemDataRole.UserRole, {'scope': scope, 'instance_id': row['instance_id']})
                    parent.setFont(0, self._terminal_font())
                    parent.setForeground(0, QBrush(QColor('#8e8e8e')))
                    parent.setIcon(0, icon('workspace', '#8e8e8e', 14))
                    wanted.add(instance_key); instances[instance_key] = parent
                    parent.setExpanded(True)
                key = ('terminal', scope, *row['key'])
                session, definition = row['session'], row['definition']
                name = session.name if session else definition.name
                item = self._item(key, parent, name)
                wanted.add(key)
                item.setData(0, Qt.ItemDataRole.UserRole, row)
                self._row_data[key] = row
                state = row['state']
                color = {'running': '#4fd18b', 'starting': '#d9a441', 'failed': '#ff7b8a'}.get(state, '#8e8e8e')
                item.setIcon(0, icon('terminal', color, 16))
                item.setToolTip(0, f'{name} · {state} · {len(session.listeners) if session else 0} ports')
                item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                monospace_font = self.tree.font(); monospace_font.setFamily('Consolas')
                item.setFont(1, monospace_font)
                item.setFont(0, self._terminal_font())
                if active is not None and session is active and not keep_selection:
                    self.tree.setCurrentItem(item)
            group.setExpanded(scope in expanded)
        for key in reversed(list(self._items)):
            if key not in wanted:
                item = self._items.pop(key)
                self._row_data.pop(key, None)
                if item.parent(): item.parent().removeChild(item)
                else: self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        for index, group in enumerate(order):
            old = self.tree.indexOfTopLevelItem(group)
            if old != index:
                self.tree.takeTopLevelItem(old); self.tree.insertTopLevelItem(index, group)
        if keep_selection and selected_key in self._items:
            self.tree.setCurrentItem(self._items[selected_key])
        elif active is None:
            self.tree.setCurrentItem(self._items.get(('workspace', navigation.selected)))
        self.tree.blockSignals(False)
        self.update_durations()
        self._action_states()
        self._refresh_row_actions()

    def _current_changed(self, current, previous):
        self._action_states()
        if self.tree.hasFocus():
            self._sync_actions_to_item(current)

    def _row_action(self, action):
        item = self._actions_item
        if item is None or not any(item is value for value in self._items.values()):
            self.row_actions.hide()
            return
        row = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if 'definition' in row:
            self.terminalAction.emit(action, row)

    def _sync_actions_to_item(self, item):
        if item is None or not any(item is value for value in self._items.values()):
            self._actions_item = None
            self.row_actions.hide()
            return
        row = item.data(0, Qt.ItemDataRole.UserRole) or {}
        rectangle = self.tree.visualItemRect(item)
        viewport = self.tree.viewport().rect()
        if 'definition' not in row or rectangle.isEmpty() or not viewport.intersects(rectangle):
            self._actions_item = None
            self.row_actions.hide()
            return
        self._actions_item = item
        self.row_actions.configure(row)
        self.row_actions.move(max(0, viewport.right() - self.row_actions.width() - 2),
                              rectangle.top() + max(0, (rectangle.height() - self.row_actions.height()) // 2))
        self.row_actions.show()
        self.row_actions.raise_()

    def _refresh_row_actions(self):
        focus = QApplication.focusWidget()
        pointer_on_actions = self.row_actions.underMouse() or any(button.underMouse() for button in self.row_actions.buttons.values())
        if self.row_actions.isVisible() and (pointer_on_actions or (focus and self.row_actions.isAncestorOf(focus))):
            self._sync_actions_to_item(self._actions_item)
        elif self.tree.viewport().underMouse():
            self._sync_actions_to_item(self.tree.itemAt(self.tree.viewport().mapFromGlobal(QCursor.pos())))
        elif self.tree.hasFocus():
            self._sync_actions_to_item(self.tree.currentItem())
        else:
            self.row_actions.hide()

    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self.tree.viewport():
            if kind in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
                self._sync_actions_to_item(self.tree.itemAt(event.position().toPoint()))
            elif kind in (QEvent.Type.Leave, QEvent.Type.Resize, QEvent.Type.Wheel):
                QTimer.singleShot(0, self._refresh_row_actions)
        elif obj is self.tree:
            if kind == QEvent.Type.FocusIn:
                self._sync_actions_to_item(self.tree.currentItem())
            elif kind == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self._refresh_row_actions)
        elif obj is self.row_actions or obj in self.row_actions.buttons.values():
            if kind in (QEvent.Type.Leave, QEvent.Type.FocusOut):
                QTimer.singleShot(0, self._refresh_row_actions)
        return super().eventFilter(obj, event)

    def _terminal_font(self):
        font = QFont(self.tree.font())
        font.setPointSize(10)
        return font

    def _heading_font(self):
        font = QFont(self.tree.font())
        font.setPointSize(10)
        font.setBold(True)
        return font

    def _item(self, key, parent, title):
        if key not in self._items:
            item = QTreeWidgetItem(parent if parent else self.tree)
            self._items[key] = item
        item = self._items[key]
        if item.parent() is not parent:
            previous = item.parent()
            if previous is not None:
                previous.takeChild(previous.indexOfChild(item))
            else:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
            if parent is not None:
                parent.addChild(item)
            else:
                self.tree.addTopLevelItem(item)
        item.setText(0, title)
        return item

    def update_durations(self):
        for key, row in self._row_data.items():
            item = self._items.get(key)
            if not item: continue
            session = row['session']
            seconds = session.age.seconds() if session and hasattr(session, 'age') else None
            value = format_duration(seconds)
            if item.text(1) != value: item.setText(1, value)
            item.setToolTip(1, f'{seconds} seconds since shell launch' if seconds is not None else 'Not started')

    def _clicked(self, item, column):
        row = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if row.get('session'): self.terminalSelected.emit(row['session'])
        else: self.scopeSelected.emit(row.get('scope', OTHER))

    def _selected_action(self, action):
        item = self.tree.currentItem()
        row = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if row and 'definition' in row: self.terminalAction.emit(action, row)

    def _remove_current(self):
        item = self.tree.currentItem()
        row = item.data(0, Qt.ItemDataRole.UserRole) if item else {}
        scope = row.get('scope')
        if scope and scope != OTHER: self.workspaceRemoved.emit(scope)

    def _action_states(self):
        if self._actions_item is not None and any(item is self._actions_item for item in self._items.values()):
            row = self._actions_item.data(0, Qt.ItemDataRole.UserRole) or {}
            self.row_actions.configure(row)

    def _menu(self, point):
        item = self.tree.itemAt(point)
        if not item: return
        self.tree.setCurrentItem(item)
        row = item.data(0, Qt.ItemDataRole.UserRole) or {}
        menu = QMenu(self)
        if 'definition' in row:
            session = row.get('session')
            if session:
                menu.addAction('Focus terminal', lambda: self.terminalSelected.emit(session))
                menu.addAction('Rename', lambda: self.terminalAction.emit('rename', row))
                if session.state in ('failed', 'exited'):
                    menu.addAction('Retry fresh shell', lambda: self.terminalAction.emit('retry', row))
                menu.addAction('Close terminal', lambda: self.terminalAction.emit('close', row))
            else: menu.addAction('Start terminal', lambda: self.terminalAction.emit('start', row))
            if row.get('definition'):
                menu.addAction('Edit saved definition', lambda: self.terminalAction.emit('edit', row))
                menu.addAction('Start another copy of this terminal', lambda: self.terminalAction.emit('copy-terminal', row))
        if row.get('scope', OTHER) != OTHER:
            menu.addSeparator()
            menu.addAction('Remove workspace from sidebar (keep profile)', self._remove_current)
        menu.exec(self.tree.viewport().mapToGlobal(point))

    def _expansion(self, item):
        expanded = [key[1] for key, widget in self._items.items() if key[0] == 'workspace' and widget.isExpanded()]
        self.expansionChanged.emit(expanded)
