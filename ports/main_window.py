"""Desktop coordinator: profiles, persistent terminals, tabs-only navigation."""

from __future__ import annotations

import base64
import time
import uuid

from PyQt6.QtCore import QByteArray, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from . import config_store
from .background import BackgroundWork, collect_snapshot
from .header_bar import HeaderBar
from .http_probe import ProbePool
from .icons import app_icon, brand_mark
from .motion import reduced_motion
from .port_monitor import filter_noise
from .process_control import kill_windows, redact_cmdline
from .profile_dialog import ProfileDialog
from .preferences import PreferencesDialog
from .profiles import TerminalProfile, WorkspaceProfile
from .session_manager import SessionManager
from .session_tabs import TabStrip
from .sidebar import Sidebar, button
from .overlays import Toast
from .terminal_pane import TerminalPane
from .theme import SPACE_2, SPACE_3, TEXT_MUTED
from .workspace_navigation import WorkspaceNavigation, OTHER
from .ports_inspector import PortsInspector


from .navigation_actions import NavigationActions

class MainWindow(NavigationActions, QMainWindow):
    probeResult = pyqtSignal(str, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ports")
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self.config = config_store.load()
        self.navigation = WorkspaceNavigation(self.config.loaded_workspace_ids if self.config.loaded_workspace_ids is not None else [p.id for p in self.config.profiles], self.config.selected_workspace_id)
        self._default_instances = {}
        self.manager = SessionManager(self)
        self.work = BackgroundWork(self)
        self.work.completed.connect(self._completed)
        self._cleanup_callback = None
        self._polling = False
        self._closing = False
        self._approved_close = False
        self._all_listeners = []
        self._external = []
        self._probe_enabled = set()
        self._probe_last, self._health = {}, {}
        self._panes: dict[str, TerminalPane] = {}
        self._unseen: set[str] = set()
        self._scan_started = 0.0
        self._scan_error = ""
        self.motion_disabled = reduced_motion(
            getattr(self.config, "reduced_motion", "system"))
        self.probeResult.connect(self._probe_result)
        self.probes = ProbePool(
            lambda key, result: self.probeResult.emit(key, result))

        self.splitter = QSplitter()
        self.splitter.setHandleWidth(1)
        self.sidebar = Sidebar()
        self.splitter.addWidget(self.sidebar)

        workspace = QWidget()
        workspace.setObjectName("workspace")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = HeaderBar()
        layout.addWidget(self.header)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        self.tabs = TabStrip()
        layout.addWidget(self.tabs)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_empty_state())
        layout.addWidget(self.stack, 1)

        self.toast = Toast(self)
        self.toast.setVisible(False)

        self.footer = self._build_footer()
        layout.addWidget(self.footer)

        self.splitter.addWidget(workspace)
        self.inspector = PortsInspector()
        self.inspector.probe_enabled = self._probe_enabled
        self.inspector.external_open = self.config.external_group_open
        self.inspector.scope.setCurrentIndex(1 if self.config.managed_ports_scope == 'all' else 0)
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([240, 800, 240])
        self.setCentralWidget(self.splitter)
        # Do not let the combined side-panel hints prevent the resize event
        # that auto-hides the right panel below 1000px.
        from PyQt6.QtWidgets import QLayout
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setMinimumWidth(760)

        self._wire()
        self.sidebar.set_profiles(self.config.profiles)
        self.splitter.setSizes([self.config.left_sidebar_width, 740, self.config.ports_inspector_width])
        self.splitter.setCollapsible(0, False)
        self._apply_panel_visibility()
        self._sync_workspace_panel()
        self._motion()
        for attr, function in (("geometry", self.restoreGeometry),
                               ("splitter", self.splitter.restoreState)):
            value = getattr(self.config, attr, None)
            if value:
                try:
                    raw = (base64.b64decode(value)
                           if isinstance(value, str) else value)
                    function(QByteArray(raw))
                except (ValueError, TypeError):
                    pass
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.age_timer = QTimer(self)
        self.age_timer.setInterval(1000)
        self.age_timer.timeout.connect(self.sidebar.update_durations)
        self.age_timer.start()
        self._refresh_footer()
        QTimer.singleShot(0, self._startup)
        # Wrapped labels need their height reserved after the stylesheet has
        # been applied, otherwise the last line is clipped by the next row.
        QTimer.singleShot(0, self._fit_empty_caption)

    def _fit_empty_caption(self) -> None:
        empty = self.stack.widget(0)
        for label in empty.findChildren(QLabel):
            if 'Save a workspace' in (label.text() or ''):
                label.setMinimumHeight(
                    label.heightForWidth(label.width()) + 2)
                return

    # -- construction ---------------------------------------------------

    def _build_empty_state(self) -> QWidget:
        empty = QWidget()
        layout = QVBoxLayout(empty)
        layout.setSpacing(SPACE_3)
        layout.addStretch(1)
        mark = QLabel()
        mark.setPixmap(brand_mark(64))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet("opacity:0.28;")
        layout.addWidget(mark)
        headline = QLabel("A home for your local servers")
        headline.setObjectName("emptyTitle")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(headline)
        caption = QLabel(
            "Save a workspace, launch your terminals, and know which process "
            "owns every port.")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setWordWrap(True)
        caption.setFixedWidth(420)
        caption.setObjectName("emptyBody")
        caption.setContentsMargins(16, 0, 16, 0)
        layout.addWidget(caption, alignment=Qt.AlignmentFlag.AlignHCenter)
        create = button("Create workspace profile", "workspace",
                        lambda: self.profile_action("new", ""), "primary")
        layout.addWidget(create, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return empty

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("footer")
        footer.setFixedHeight(24)
        row = QHBoxLayout(footer)
        row.setContentsMargins(SPACE_3, 0, SPACE_3, 0)
        row.setSpacing(SPACE_2)
        self.footer_sessions = QLabel("0 sessions")
        self.footer_sessions.setObjectName("footerText")
        self.footer_ports = QLabel("0 ports")
        self.footer_ports.setObjectName("footerText")
        self.footer_scan = QLabel("Scanning")
        self.footer_scan.setObjectName("footerText")
        self.footer_shell = QLabel("")
        self.footer_shell.setObjectName("footerText")
        for label in (self.footer_sessions, self.footer_ports,
                      self.footer_scan):
            row.addWidget(label)
        row.addStretch(1)
        row.addWidget(self.footer_shell)
        keys = QPushButton("Shortcuts  Ctrl+/")
        keys.setObjectName("rowAction")
        keys.setStyleSheet(f"color:{TEXT_MUTED}; padding:0 6px;")
        keys.setCursor(Qt.CursorShape.PointingHandCursor)
        keys.setAccessibleName("Keyboard shortcuts")
        keys.clicked.connect(self.show_shortcuts)
        row.addWidget(keys)
        return footer

    def _wire(self) -> None:
        sidebar = self.sidebar
        sidebar.newSessionRequested.connect(self._create_ad_hoc)
        sidebar.profileAction.connect(self.profile_action)
        sidebar.settingsRequested.connect(self.settings)
        sidebar.shortcutSheetRequested.connect(self.show_shortcuts)
        sidebar.scopeSelected.connect(self.select_scope)
        sidebar.terminalSelected.connect(self.focus_session)
        sidebar.terminalAction.connect(self._tree_action)
        sidebar.workspaceRemoved.connect(self.unpin_workspace)
        sidebar.expansionChanged.connect(self._expansion_changed)
        self.splitter.splitterMoved.connect(self._panel_resized)
        panel = self.inspector
        panel.findPort.connect(self.find_port)
        panel.openUrl.connect(self.open_port)
        panel.copyUrl.connect(self.copy_port)
        panel.killRequested.connect(self.kill_listener)
        panel.labelEditRequested.connect(self.edit_label)
        panel.probeToggled.connect(self.toggle_probe)
        panel.externalStateChanged.connect(self._external_group_changed)
        panel.scopeChanged.connect(self._ports_scope_changed)
        panel.ownerRequested.connect(lambda sid: self.focus_session(self.session(sid)))
        panel.visibilityChanged.connect(self._panel_visibility_changed)

        self.manager.sessionAdded.connect(self.added)
        self.manager.sessionRemoved.connect(self.removed)
        self.manager.activeChanged.connect(self.active_changed)
        self.manager.orderChanged.connect(self.refresh_navigation)

        self.tabs.selected.connect(
            lambda sid: self.manager.set_active(self.session(sid)))
        self.tabs.closeRequested.connect(
            lambda sid: self.close_session(self.session(sid)))
        self.tabs.renameRequested.connect(self.rename)
        self.tabs.orderRequested.connect(self._reorder_visible)
        self.tabs.newTerminalRequested.connect(self.sidebar.new_terminal)

        self.header.restartRequested.connect(self.restart)
        self.header.ctrlCRequested.connect(
            lambda: self.manager.active and self.manager.active.send_ctrl_c())
        self.header.clearRequested.connect(
            lambda: self.manager.active and self.manager.active.clear())
        self.header.killPortRequested.connect(self.kill_active)
        self.header.copyPathRequested.connect(self.copy_folder)
        self.header.openFolderRequested.connect(self.open_folder)
        self.header.openPortRequested.connect(
            lambda port: self.open_port(
                self.manager.active.id if self.manager.active else "", port))
        self.header.portMenuRequested.connect(self._header_port_menu)
        self.header.killListenerRequested.connect(self.kill_listener)
        self.header.panelToggleRequested.connect(self.toggle_workspace_panel)

        for sequence, callback in (
            ("Ctrl+Shift+T", sidebar.new_terminal),
            ("Ctrl+F", self.open_search),
            ("Ctrl+W", lambda: self.close_session(self.manager.active)),
            ("Ctrl+Tab", lambda: self.cycle(1)),
            ("Ctrl+Shift+Tab", lambda: self.cycle(-1)),
            ("Ctrl+K", self.show_palette),
            ("Ctrl+/", self.show_shortcuts),
            ("Ctrl+Shift+E", self.toggle_workspace_panel),
            ("Ctrl+=", lambda: self.set_terminal_font(1)),
            ("Ctrl+-", lambda: self.set_terminal_font(-1)),
        ):
            QShortcut(QKeySequence(sequence), self).activated.connect(callback)
        for index in range(1, 10):
            QShortcut(QKeySequence(f"Ctrl+{index}"), self).activated.connect(
                lambda i=index: self.jump_to(i))

    # -- motion / rail --------------------------------------------------

    def _motion(self) -> None:
        self.motion_disabled = reduced_motion(
            getattr(self.config, "reduced_motion", "system"))
        self.header.dot.motion_disabled = self.motion_disabled


    # -- config ---------------------------------------------------------

    def _on_selection(self, text: str) -> None:
        """Copy-on-select, honoring the user's preference."""
        if not getattr(self.config, "copy_on_select", True):
            return
        if text.strip():
            QApplication.clipboard().setText(text)
            self.footer_scan.setText("Selection copied")

    def save_config(self) -> bool:
        if not config_store.save(self.config):
            self.footer_scan.setText(
                "Settings not saved: " + getattr(self.config, "last_error", "read-only"))
            return False
        return True

    def _startup(self) -> None:
        if self.config.warning:
            QMessageBox.warning(self, 'Workspace navigation', self.config.warning)
        self._sync_workspace_panel()

    # -- sessions -------------------------------------------------------

    def session(self, sid: str):
        return next((s for s in self.manager.sessions if s.id == sid), None)

    def added(self, session) -> None:
        pane = TerminalPane(session, motion_disabled=self.motion_disabled)
        session.changed.connect(lambda s=session: self.refresh_session(s))
        session.start(self.config.scrollback_lines, asynchronous=True)
        if session.view is not None:
            pane.attach_view(session.view)
            session.view.set_font_size(
                getattr(self.config, "terminal_font_size", 13))
            session.view.selectionCopied.connect(self._on_selection)
        else:
            pane.layout().addWidget(QLabel("Terminal view unavailable"))
        pane.restartRequested.connect(
            lambda s=session: self._pane_restart(s))
        pane.retryRequested.connect(lambda s=session: self.retry(s.id))
        pane.closeRequested.connect(
            lambda sid: self.close_session(self.session(sid)))
        self._panes[session.id] = pane
        self.stack.addWidget(pane)
        self._unseen.discard(session.id)
        self.refresh_navigation()

    def removed(self, sid: str) -> None:
        pane = self._panes.pop(sid, None)
        if pane is not None:
            self.stack.removeWidget(pane)
            pane.deleteLater()
        self._unseen.discard(sid)
        if self.manager.active is None or self.navigation.scope(self.manager.active) != self.navigation.selected:
            self.manager.set_active(self.navigation.active(self.manager.sessions))
        self.refresh_navigation()

    def active_changed(self, session) -> None:
        if session is not None:
            self.navigation.select(self.navigation.scope(session))
            self.navigation.remember(session)
        self.header.set_session(session)
        if session is not None and session.id in self._panes:
            self._unseen.discard(session.id)
            self.stack.setCurrentWidget(self._panes[session.id])
            if session.view is not None:
                session.view.refit()
                session.view.focus_terminal()
        else:
            self.stack.setCurrentIndex(0)
        self.tabs.sync(self.visible_sessions(), session, self._unseen)
        self._sync_workspace_panel()
        self._refresh_footer()

    def refresh_session(self, session) -> None:
        if session not in self.manager.sessions:
            return
        pane = self._panes.get(session.id)
        if pane is not None:
            pane.sync_failure()
        if session is self.manager.active:
            self.header.set_session(session)
        elif session.state == "running":
            self._unseen.add(session.id)
        self._refresh_merged_ports()
        self.tabs.sync(self.visible_sessions(), self.manager.active, self._unseen)
        self._sync_workspace_panel()
        self._refresh_footer()

    def refresh_navigation(self) -> None:
        self.tabs.sync(self.visible_sessions(), self.manager.active, self._unseen)
        self._sync_workspace_panel()
        self._refresh_footer()

    def _refresh_footer(self) -> None:
        sessions = self.manager.sessions
        ports = {l.port for s in sessions for l in s.listeners}
        self.footer_sessions.setText(f"{len(sessions)} sessions")
        self.footer_ports.setText(f"{len(ports)} ports")
        active = self.manager.active
        self.footer_shell.setText(active.shell if active else "")
        if self._scan_error:
            self.footer_scan.setText(f"Stale · {self._scan_error}"[:60])
        elif not self._scan_started:
            self.footer_scan.setText("Scanning")
        else:
            age = max(0, int(time.monotonic() - self._scan_started))
            self.footer_scan.setText(f"Scanned {age}s ago")

    # -- commands -------------------------------------------------------

    def rename(self, sid: str) -> None:
        session = self.session(sid)
        if not session:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename terminal", "Name", text=session.name)
        if accepted and name.strip():
            session.name = name.strip()[:120]
            self.refresh_session(session)

    def move(self, sid: str, offset: int) -> None:
        identifiers = [s.id for s in self.manager.sessions]
        index = identifiers.index(sid)
        target = index + offset
        if 0 <= target < len(identifiers):
            identifiers[index], identifiers[target] = (
                identifiers[target], identifiers[index])
            self.manager.reorder(identifiers)

    def cycle(self, offset: int) -> None:
        sessions = self.visible_sessions()
        if not sessions:
            return
        index = (sessions.index(self.manager.active)
                 if self.manager.active in sessions else 0)
        self.manager.set_active(sessions[(index + offset) % len(sessions)])

    def jump_to(self, position: int) -> None:
        sessions = self.visible_sessions()
        if position <= len(sessions):
            self.manager.set_active(sessions[position - 1])

    def retry(self, sid: str) -> None:
        session = self.session(sid)
        if session and session.state in ("failed", "exited"):
            session.prepare_close()
            self.work.submit(session.close,
                             lambda _: self._retry_closed(session))

    def _retry_closed(self, session) -> None:
        replacement = self.manager.create(
            session.shell, session.cwd, session.name, session.startup_cmd,
            session.distro, definition_id=session.definition_id,
            profile_id=session.profile_id, instance_id=session.instance_id,
            accent=session.accent, restart_cmd=session.restart_cmd,
            expected_ports=list(session.expected_ports))
        self._remove_session(session)
        self.manager.set_active(replacement)

    def _pane_restart(self, session) -> None:
        session.restart()

    def restart(self) -> None:
        session = self.manager.active
        if not session:
            return
        if session.shell == "cmd":
            session.send_ctrl_c()
            if QMessageBox.question(
                    self, "Confirm CMD prompt",
                    "Has the foreground command stopped and CMD returned to "
                    "its prompt? Run the saved restart command now?"
            ) == QMessageBox.StandardButton.Yes:
                session.restart(confirmed=True)
        else:
            session.restart()

    def open_search(self) -> None:
        pane = self._panes.get(self.manager.active.id) if self.manager.active else None
        if pane is not None:
            pane.open_search()

    def set_terminal_font(self, delta: int) -> None:
        view = self.manager.active.view if self.manager.active else None
        if view is None:
            return
        size = max(9, min(20, getattr(self.config, "terminal_font_size", 13) + delta))
        self.config.terminal_font_size = size
        view.set_font_size(size)
        self.save_config()

    def show_shortcuts(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard shortcuts")
        layout = QVBoxLayout(dialog)
        rows = [
            ("Ctrl+Shift+T", "New terminal"),
            ("Ctrl+W", "Close active terminal"),
            ("Ctrl+Tab / Ctrl+Shift+Tab", "Next / previous terminal"),
            ("Ctrl+1…9", "Jump to terminal"),
            ("Ctrl+F", "Find in terminal (Enter next, Shift+Enter previous)"),
            ("Ctrl+K", "Command palette"),
            ("Ctrl+Shift+E", "Show / hide ports inspector"),
            ("Ctrl+/", "This shortcut sheet"),
            ("Ctrl+= / Ctrl+-", "Terminal font size"),
        ]
        for keys, description in rows:
            line = QLabel(
                f'<span style="font-family:Consolas;color:#e6e9ee">{keys}</span>'
                f' &nbsp; {description}')
            layout.addWidget(line)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        dialog.exec()

    def show_palette(self) -> None:
        from .palette import CommandPalette
        dialog = CommandPalette(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.invoke()

    # -- folder / port actions ------------------------------------------

    def copy_folder(self) -> None:
        session = self.manager.active
        if not session:
            return
        QApplication.clipboard().setText(session.current_cwd or session.cwd)
        self.footer_scan.setText("Folder path copied")

    def open_folder(self) -> None:
        session = self.manager.active
        if not session:
            return
        target = session.current_cwd or session.cwd
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _header_port_menu(self, port: int, point) -> None:
        session = self.manager.active
        if session:
            self.inspector.badge_menu(session, port, point)

    def url(self, sid: str, port: int) -> str:
        session = self.session(sid)
        listeners = session.listeners if session else self._all_listeners
        endpoint = next((l for l in listeners if l.port == port), None)
        host = "[::1]" if endpoint and ":" in endpoint.address else "localhost"
        return f"http://{host}:{port}"

    def open_port(self, sid: str, port: int) -> None:
        QDesktopServices.openUrl(QUrl(self.url(sid, port)))

    def copy_port(self, sid: str, port: int) -> None:
        QApplication.clipboard().setText(self.url(sid, port))
        self.footer_scan.setText(f"Copied URL for :{port}")

    def find_port(self, port: int) -> None:
        self.work.submit(
            lambda: collect_snapshot(tuple(self.manager.sessions)),
            lambda result: self._show_port(port, result),
            self._snapshot_error)

    def _show_port(self, port: int, result) -> None:
        attributed, external, _, _ = result
        listeners = [l for l in external
                     + [l for group in attributed.values() for l in group]
                     if l.port == port]
        if not listeners:
            QMessageBox.information(
                self, "Port search",
                f"No accessible localhost listener on :{port}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Owners of :{port}")
        layout = QVBoxLayout(dialog)
        for listener in listeners:
            owner = listener.owner
            label = QLabel(
                f"{listener.env} {listener.distro} · {listener.address}:{port}"
                f" · {owner.name if owner else 'unknown'}"
                f" · PID {owner.pid if owner else '?'}")
            layout.addWidget(label)
            layout.addWidget(button(
                "Force kill this listener owner", "power",
                lambda l=listener: self.kill_listener(l)))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        dialog.exec()

    def kill_listener(self, listener) -> None:
        owner = listener.owner
        if not owner:
            QMessageBox.warning(self, "Cannot kill",
                                "Owner inaccessible; no process action available")
            return
        session_roots = {s.pty.pid for s in self.manager.sessions if s.pty}
        for s in self.manager.sessions:
            session_roots.update(
                p["pid"] for p in s.children
                if p.get("name", "").lower() in
                ("powershell.exe", "pwsh.exe", "cmd.exe"))
        text = (
            "Force termination affects every listener owned by this process."
            f"\n\nEnvironment: {owner.env} {owner.distro}"
            f"\nPID: {owner.pid}\nProcess: {owner.name}"
            f"\nEndpoint: {listener.address}:{listener.port}"
            f"\nStart identity: {owner.create_time}"
            "\n\nParent shell is protected. A watcher may restart this process.")
        question = QMessageBox(self)
        question.setWindowTitle("Confirm process termination")
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setText(text)
        question.setStandardButtons(QMessageBox.StandardButton.Yes
                                    | QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if question.exec() != QMessageBox.StandardButton.Yes:
            return
        if owner.env == "wsl":
            session = next((s for s in self.manager.sessions
                            if s.distro == owner.distro and s.wsl), None)
            if not session:
                return
            self.work.submit(
                lambda: session.wsl.send_signal(
                    owner.pid, 15, start=owner.create_time,
                    address=listener.address, port=listener.port),
                lambda value: self.footer_scan.setText(str(value)),
                lambda error: QMessageBox.warning(self, "Signal refused", error))
        else:
            self.work.submit(
                lambda: kill_windows(owner, port=listener.port,
                                     address=listener.address,
                                     protected_pids=session_roots),
                lambda result: self.footer_scan.setText(result.message),
                lambda error: QMessageBox.warning(self, "Kill failed", error))

    def kill_active(self) -> None:
        session = self.manager.active
        if not session or not session.listeners:
            return
        items = [f"{l.address}:{l.port} · "
                 f"{l.owner.name if l.owner else 'unknown'}"
                 for l in session.listeners]
        choice, accepted = QInputDialog.getItem(
            self, "Choose listener", "Process to terminate", items, 0, False)
        if accepted:
            self.kill_listener(session.listeners[items.index(choice)])

    def edit_label(self, sid: str, port: int) -> None:
        session = self.session(sid)
        if not session:
            return
        label, ok = QInputDialog.getText(
            self, "Port label", f"Label for :{port}",
            text=self.config.get_label(session.label_scope, port))
        if ok:
            self.config.set_label(session.label_scope, port, label)
            self.save_config()
            self.refresh_session(session)

    def toggle_probe(self, sid: str, port: int, enabled: bool) -> None:
        key = sid, port
        if enabled:
            self._probe_enabled.add(key)
        else:
            self._probe_enabled.discard(key)
            self._health.pop(key, None)
        self.run_probes()

    def run_probes(self) -> None:
        for sid, port in tuple(self._probe_enabled):
            session = self.session(sid)
            if not session or not any(l.port == port for l in session.listeners):
                continue
            if time.monotonic() - self._probe_last.get((sid, port), 0) >= 5:
                self._probe_last[(sid, port)] = time.monotonic()
                endpoint = next(l for l in session.listeners if l.port == port)
                self.probes.request(
                    f"{sid}:{port}", port,
                    host="::1" if ":" in endpoint.address else "127.0.0.1")

    def _probe_result(self, key: str, result) -> None:
        sid, port = key.rsplit(":", 1)
        session = self.session(sid)
        if session:
            self._health[(sid, int(port))] = result.label
            self.refresh_session(session)

    # -- profiles -------------------------------------------------------

    def profile_action(self, action: str, identifier: str, terminal_id=None) -> None:
        profile = next((p for p in self.config.profiles
                        if p.id == identifier), None)
        if action == 'manage':
            menu = QMenu(self)
            for saved in self.config.profiles:
                item = menu.addMenu(saved.name)
                item.addAction('Load in sidebar', lambda p=saved: self.load_workspace(p.id))
                item.addAction('Edit profile', lambda p=saved: self.profile_action('edit', p.id))
                item.addAction('Delete profile…', lambda p=saved: self.profile_action('delete', p.id))
            menu.exec(self.sidebar.manage_button.mapToGlobal(self.sidebar.manage_button.rect().bottomLeft()))
            return
        if action in ('run', 'copy', 'missing'):
            return  # Bulk launch intentionally removed from workspace navigation.
        if action == 'load':
            self.load_workspace(identifier)
            return
        if action == "delete" and profile:
            if QMessageBox.question(
                    self, "Delete profile",
                    f"Delete '{profile.name}'? Running terminals stay open."
            ) == QMessageBox.StandardButton.Yes:
                self.config.profiles.remove(profile)
                self.navigation.unpin(profile.id)
                self._select_current_scope()
                self._save_navigation()
                self.sidebar.set_profiles(self.config.profiles)
            return
        if action == "save":
            active = self.manager.active
            sessions = [s for s in self.manager.sessions
                        if active is None or not active.instance_id
                        or s.instance_id == active.instance_id]
            if not sessions:
                self.footer_scan.setText(
                    "Open a terminal before saving a workspace")
                return
            profile = WorkspaceProfile(
                name="Saved workspace",
                terminals=[
                    TerminalProfile(
                        name=s.name, shell=s.shell,
                        cwd=s.current_cwd or s.cwd, distro=s.distro,
                        startup_cmd=s.startup_cmd,
                        restart_cmd=s.restart_cmd, accent=s.accent,
                        expected_ports=s.expected_ports)
                    for s in sessions])
        elif action == "duplicate" and profile:
            profile = WorkspaceProfile.from_dict(profile.to_dict())
            profile.id = uuid.uuid4().hex
            profile.name += " copy"
            profile.reviewed_fingerprint = ""
            for terminal in profile.terminals:
                terminal.id = uuid.uuid4().hex
        elif action == "new":
            profile = None
        elif action != "edit" or not profile:
            return
        original_id = identifier if action == "edit" else None
        dialog = ProfileDialog(profile, self, terminal_id=terminal_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            edited = dialog.profile
            if original_id:
                index = next(i for i, p in enumerate(self.config.profiles)
                             if p.id == original_id)
                edited.revision += 1
                self.config.profiles[index] = edited
            else:
                self.config.profiles.append(edited)
            self.save_config()
            self.sidebar.set_profiles(self.config.profiles)
            self.load_workspace(edited.id)

    def _review_profile(self, profile) -> bool:
        commands = "\n\n".join(
            f"{t.name}\nShell: {t.shell} {t.distro}\n"
            f"Folder: {t.cwd or '(home)'}\n"
            f"Startup: {redact_cmdline(t.startup_cmd) or '(none)'}\n"
            f"Restart: {redact_cmdline(t.restart_cmd) or '(startup command)'}"
            for t in profile.terminals)
        dialog = QDialog(self)
        dialog.setWindowTitle("Review workspace commands")
        dialog.resize(700, 440)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(commands)
        text.setReadOnly(True)
        layout.addWidget(text)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                    | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Approve and run")
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        profile.approve()
        self.save_config()
        return True

    # -- monitoring -----------------------------------------------------

    def poll(self) -> None:
        if self._polling or self._closing:
            return
        self._polling = True
        self._scan_started = time.monotonic()
        sessions = tuple(self.manager.sessions)
        self.work.submit(lambda: collect_snapshot(sessions),
                         self._snapshot, self._snapshot_error)

    # -- workspace panel --------------------------------------------------

    def _selected_profile(self):
        return next((p for p in self.config.profiles if p.id == self.navigation.selected), None)

    def _sync_workspace_panel(self) -> None:
        self._apply_panel_visibility()
        if self.manager.active is None:
            scope = self._selected_profile()
            self.header.title.setText(scope.name if scope else 'Other terminals')
            self.header.path.setText('No terminals started — select a definition and Start')
        self.sidebar.sync(self.config.profiles, self.navigation, self.manager.sessions,
                          self.config.expanded_workspace_ids, self.manager.active)

    def _apply_panel_visibility(self):
        if not hasattr(self, 'inspector'): return
        visible = bool(self.config.ports_inspector_visible and self.width() >= 1000)
        changed = self.inspector.isHidden() == visible
        self.inspector.setVisible(visible)
        self.header.panel_button.setChecked(visible)
        if changed and visible:
            rail = self.splitter.sizes()[0] or self.config.left_sidebar_width
            panel = self.config.ports_inspector_width
            self.splitter.setSizes([rail, max(300, self.width() - rail - panel), panel])

    def _panel_resized(self, position, index):
        self.config.left_sidebar_width = max(220, min(420, self.sidebar.width()))
        if self.inspector.isVisible():
            self.config.ports_inspector_width = max(220, min(420, self.inspector.width()))
        self.save_config()

    def _panel_activated(self, row) -> None:
        session = row.get("session")
        if session is not None:
            self.manager.set_active(session)

    def _panel_rename(self, row) -> None:
        session = row.get("session")
        if session is not None:
            self.rename(session.id)

    def _panel_close(self, row) -> None:
        session = row.get("session")
        if session is not None:
            self.close_session(session)

    def _panel_start(self, row) -> None:
        """Start a stopped definition through the reviewed launch path."""
        profile = next((p for p in self.config.profiles if p.id == row.get('scope', self.navigation.selected)), None)
        if profile is None:
            return
        definition = row.get('definition')
        if definition is None or definition.id not in {d.id for d in profile.terminals}:
            return
        if profile.needs_review() and not self._review_profile(profile):
            return
        instance = row.get('instance_id', '')
        if not instance:
            instance = next((s.instance_id for s in self.manager.sessions if s.profile_id == profile.id), None)
            if not instance:
                instance = self._default_instances.setdefault(profile.id, uuid.uuid4().hex)
        self.manager.launch_definition(profile, definition.id, instance)
        self._sync_workspace_panel()

    def _panel_retry(self, row) -> None:
        session = row.get("session")
        if session is not None:
            self.retry(session.id)

    def _panel_edit(self, row) -> None:
        profile = next((p for p in self.config.profiles if p.id == row.get('scope', self.navigation.selected)), None)
        if profile is None:
            return
        definition = row.get('definition')
        self.profile_action("edit", profile.id, terminal_id=definition.id if definition else None)

    def _panel_run(self) -> None:
        self.sidebar.load_selected()

    def _panel_visibility_changed(self, visible: bool) -> None:
        self.config.ports_inspector_visible = bool(visible)
        self._apply_panel_visibility()
        self.save_config()

    def toggle_workspace_panel(self) -> None:
        self._panel_visibility_changed(not self.config.ports_inspector_visible)

    def _external_group_changed(self, open_: bool) -> None:
        self.config.external_group_open = bool(open_)
        self.save_config()

    def _refresh_merged_ports(self) -> None:
        """Single call site that renders session and external ports together."""
        sessions = self.manager.sessions if self.config.managed_ports_scope == 'all' else self.visible_sessions()
        labels = {(s.id, l.port): self.config.get_label(s.label_scope, l.port)
                  for s in sessions for l in s.listeners}
        self.inspector.update_ports(sessions, labels, self.inspector.external_listeners())

    def _ports_scope_changed(self, scope):
        self.config.managed_ports_scope = scope
        self._refresh_merged_ports()
        self.save_config()

    def _snapshot_error(self, error: str) -> None:
        self._polling = False
        self._scan_error = error
        self._refresh_footer()

    def _snapshot(self, result) -> None:
        self._polling = False
        self._scan_error = ""
        attributed, external, children, errors = result
        previous = {(s.id, l.port) for s in self.manager.sessions
                    for l in s.listeners}
        self._external = external
        self._all_listeners = list(external)
        for session in self.manager.sessions:
            session.listeners = attributed.get(session.id, [])
            session.children = children.get(session.id, [])
            session.child_name = (session.children[-1]["name"]
                                  if session.children else "")
            self.inspector.set_listeners(session.id, session.listeners)
            self._all_listeners.extend(session.listeners)
            self.refresh_session(session)
        # Presentation filtering still applies only to the external group; the
        # merged list keeps session-owned ports always visible.
        self.inspector.update_external(
            [l for l in external
             if filter_noise(l, self.config.process_denylist,
                             self.config.process_allowlist)])
        self._refresh_merged_ports()
        if errors:
            self._scan_error = errors[0]
        current = {(s.id, l.port) for s in self.manager.sessions
                   for l in s.listeners}
        added = current - previous
        removed = previous - current
        if added or removed:
            self._notify_port_changes(added, removed)
        self.run_probes()
        self._refresh_footer()

    def _notify_port_changes(self, added: set, removed: set) -> None:
        """One toast per batch, collapsing bursts into a summary."""
        names = {s.id: s.name for s in self.manager.sessions}

        def describe(items, verb: str) -> str:
            ordered = sorted(items)
            ports = ", ".join(f":{port}" for _, port in ordered[:3])
            if len(ordered) > 3:
                ports += f" +{len(ordered) - 3} more"
            owner = names.get(ordered[0][0], "")
            label = f"{owner} " if owner and len({sid for sid, _ in ordered}) == 1 else ""
            return f"{label}{verb} {ports}"

        parts = []
        if added:
            parts.append(describe(added, "listening on"))
        if removed:
            parts.append(describe(removed, "closed"))
        self.toast.show_message(" · ".join(parts), self.motion_disabled)
        self._position_toast()

    def _position_toast(self) -> None:
        margin = SPACE_3
        self.toast.adjustSize()
        area = self.stack.geometry()
        self.toast.move(
            area.right() - self.toast.width() - margin,
            area.bottom() - self.toast.height() - margin)
        self.toast.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'inspector'):
            self._apply_panel_visibility()
        if hasattr(self, 'toast') and self.toast.isVisible():
            self._position_toast()

    # -- closing --------------------------------------------------------

    def close_session(self, session) -> None:
        if not session or session.state == "stopping":
            return
        if session.state not in ("exited", "failed") and \
                QMessageBox.question(
                    self, "Close terminal",
                    f"Close '{session.name}' and stop its owned processes?"
                ) != QMessageBox.StandardButton.Yes:
            return
        session.state = "stopping"
        session.prepare_close()
        self.refresh_session(session)
        self.work.submit(session.close, lambda _: self._remove_session(session))

    def _remove_session(self, session):
        if self.manager.active is session:
            remaining = [s for s in self.visible_sessions() if s is not session]
            self.manager.set_active(remaining[0] if remaining else None)
        self.manager.close(session)

    def settings(self) -> None:
        dialog = PreferencesDialog(self.config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._motion()
        self.splitter.setSizes([self.config.left_sidebar_width, 740, self.config.ports_inspector_width])
        self.splitter.setCollapsible(0, False)
        self._apply_panel_visibility()
        self._sync_workspace_panel()
        for session in list(self.manager.sessions):
            if session.view is not None:
                session.view.set_font_size(self.config.terminal_font_size)
        self._refresh_footer()

    def _completed(self, callback, value, error) -> None:
        if self._closing:
            if callback == self._cleanup_callback:
                self._finish_close(value)
            return
        if callback:
            callback(error if error else value)

    def closeEvent(self, event) -> None:
        if self._approved_close:
            event.accept()
            return
        event.ignore()
        if self._closing:
            return
        if self.manager.sessions and QMessageBox.question(
                self, "Quit Ports",
                "Quit and stop all Ports-owned terminal sessions? "
                "External processes remain untouched."
        ) != QMessageBox.StandardButton.Yes:
            return
        self.config.loaded_workspace_ids = list(self.navigation.loaded)
        self.config.selected_workspace_id = self.navigation.selected
        self.age_timer.stop()
        self.config.geometry = base64.b64encode(
            bytes(self.saveGeometry())).decode()
        self.config.splitter = base64.b64encode(
            bytes(self.splitter.saveState())).decode()
        self.save_config()
        self.timer.stop()
        self.probes.close()
        sessions = tuple(self.manager.sessions)
        for session in sessions:
            session.prepare_close()
        self.setEnabled(False)
        self._closing = True

        def cleanup():
            for session in sessions:
                session.close()
            return True

        self._cleanup_callback = self._finish_close
        self.work.submit(cleanup, self._finish_close, self._finish_close)

    def _finish_close(self, _) -> None:
        self._approved_close = True
        self.work.close()
        self.close()
