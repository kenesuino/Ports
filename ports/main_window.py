"""Desktop coordinator: profiles, persistent views and asynchronous controls."""
from copy import deepcopy
import base64
import time
import uuid

from PyQt6.QtCore import QByteArray, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                            QDialogButtonBox, QFormLayout, QInputDialog, QLabel,
                            QMainWindow, QMessageBox, QPlainTextEdit, QSplitter,
                            QStackedWidget, QVBoxLayout, QWidget)

from . import config_store
from .background import BackgroundWork, collect_snapshot
from .header_bar import HeaderBar
from .http_probe import ProbePool
from .icons import app_icon
from .motion import HoverButton, reduced_motion
from .port_monitor import filter_noise
from .process_control import kill_windows, redact_cmdline
from .profile_dialog import ProfileDialog
from .profiles import TerminalProfile, WorkspaceProfile
from .session_manager import SessionManager
from .session_tabs import SessionTabs
from .sidebar import Sidebar, button


class MainWindow(QMainWindow):
    probeResult = pyqtSignal(str, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ports · Local development")
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self.config = config_store.load()
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
        self.probeResult.connect(self._probe_result)
        self.probes = ProbePool(lambda key, result: self.probeResult.emit(key, result))
        self.splitter = QSplitter()
        self.sidebar = Sidebar()
        self.sidebar.probe_enabled = self._probe_enabled
        self.splitter.addWidget(self.sidebar)
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = HeaderBar()
        self.tabs = SessionTabs()
        self.stack = QStackedWidget()
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch()
        headline = QLabel("A home for your local servers")
        headline.setObjectName("emptyTitle")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(headline)
        caption = QLabel("Save a workspace. Launch your terminals. Know which process owns every port.")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setWordWrap(True)
        caption.setObjectName("muted")
        empty_layout.addWidget(caption)
        create = button("Create workspace profile", "workspace", lambda: self.profile_action("new", ""))
        empty_layout.addWidget(create, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch()
        self.stack.addWidget(empty)
        layout.addWidget(self.header)
        layout.addWidget(self.tabs)
        layout.addWidget(self.stack, 1)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([300, 980])
        self.setCentralWidget(self.splitter)
        self.statusBar().showMessage("Local-only · explicit commands · protected process controls")
        self._wire()
        self.sidebar.set_profiles(self.config.profiles)
        self.header.mode.setCurrentIndex(1 if self.config.view_mode == "tabs" else 0)
        self.set_mode(self.config.view_mode)
        self._motion()
        for attr, function in [("geometry", self.restoreGeometry), ("splitter", self.splitter.restoreState)]:
            value = getattr(self.config, attr, None)
            if value:
                try:
                    raw = base64.b64decode(value) if isinstance(value, str) else value
                    function(QByteArray(raw))
                except (ValueError, TypeError):
                    pass
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        QTimer.singleShot(0, self._startup)

    def _wire(self):
        sidebar = self.sidebar
        sidebar.newSessionRequested.connect(lambda v: self.manager.create(**v))
        sidebar.sessionSelected.connect(self.manager.set_active)
        sidebar.sessionCloseRequested.connect(self.close_session)
        sidebar.renameRequested.connect(self.rename)
        sidebar.retryRequested.connect(self.retry)
        sidebar.moveRequested.connect(self.move)
        sidebar.profileAction.connect(self.profile_action)
        sidebar.settingsRequested.connect(self.settings)
        sidebar.findPort.connect(self.find_port)
        sidebar.openUrl.connect(self.open_port)
        sidebar.copyUrl.connect(self.copy_port)
        sidebar.killRequested.connect(self.kill_listener)
        sidebar.labelEditRequested.connect(self.edit_label)
        sidebar.probeToggled.connect(self.toggle_probe)
        self.manager.sessionAdded.connect(self.added)
        self.manager.sessionRemoved.connect(self.removed)
        self.manager.activeChanged.connect(self.active_changed)
        self.manager.orderChanged.connect(self.refresh_navigation)
        self.tabs.selected.connect(lambda sid: self.manager.set_active(self.session(sid)))
        self.tabs.closeRequested.connect(lambda sid: self.close_session(self.session(sid)))
        self.tabs.renameRequested.connect(self.rename)
        self.tabs.orderRequested.connect(self.manager.reorder)
        self.header.modeChanged.connect(self.set_mode)
        self.header.restartRequested.connect(self.restart)
        self.header.ctrlCRequested.connect(lambda: self.manager.active and self.manager.active.send_ctrl_c())
        self.header.clearRequested.connect(lambda: self.manager.active and self.manager.active.clear())
        self.header.killPortRequested.connect(self.kill_active)
        self.header.searchRequested.connect(lambda text: self.manager.active and self.manager.active.view.search(text))
        for sequence, callback in [("Ctrl+Shift+T", sidebar.new_terminal), ("Ctrl+Shift+F", self.header.search_edit.setFocus),
                                    ("Ctrl+W", lambda: self.close_session(self.manager.active)),
                                    ("Ctrl+Tab", lambda: self.cycle(1)), ("Ctrl+Shift+Tab", lambda: self.cycle(-1))]:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)

    def _completed(self, callback, value, error):
        if self._closing:
            if callback == self._cleanup_callback:
                self._finish_close(value)
            return
        if callback:
            callback(error if error else value)

    def _startup(self):
        if getattr(self.config, "warning", ""):
            QMessageBox.warning(self, "Configuration recovery", self.config.warning + "\nOriginal file retained; use Preferences to recover before saving.")
        if self.config.saved_sessions and QMessageBox.question(self, "Restore layout", "Restore previous terminal layout? Fresh shells only; saved startup commands will not run.") == QMessageBox.StandardButton.Yes:
            for saved in self.config.saved_sessions:
                session = self.manager.create(saved.shell, saved.cwd, saved.name, "", saved.distro,
                                              definition_id=saved.id, profile_id=saved.workspace_profile_id,
                                              instance_id=saved.instance_id, accent=saved.accent)
                # Restore definitions after shell startup has been configured,
                # without arming the automatic startup path.
                session.startup_cmd = saved.startup_cmd
                session.restart_cmd = saved.restart_cmd or saved.startup_cmd

    def save_config(self):
        if not config_store.save(self.config):
            self.statusBar().showMessage("Settings not saved: " + getattr(self.config, "last_error", "configuration is read-only"))
            return False
        return True

    def _motion(self):
        setting = getattr(self.config, "reduced_motion", "system")
        disabled = reduced_motion(setting)
        self.sidebar.motion_disabled = disabled
        for control in self.findChildren(HoverButton):
            control.motion_disabled = disabled

    def session(self, sid):
        return next((s for s in self.manager.sessions if s.id == sid), None)

    def added(self, session):
        session.changed.connect(lambda s=session: self.refresh_session(s))
        session.start(self.config.scrollback_lines, asynchronous=True)
        self.stack.addWidget(session.view)
        self.sidebar.add_session(session)
        self._motion()
        self.refresh_navigation()

    def removed(self, sid):
        self.sidebar.remove_session(sid)
        self.refresh_navigation()

    def active_changed(self, session):
        self.sidebar.set_active(session)
        self.header.set_session(session)
        if session and session.view:
            self.stack.setCurrentWidget(session.view)
            session.view.refit()
            session.view.focus_terminal()
        else:
            self.stack.setCurrentIndex(0)
        self.tabs.sync(self.manager.sessions, session)

    def refresh_session(self, session):
        if session not in self.manager.sessions:
            return
        labels = {l.port: self.config.get_label(session.label_scope, l.port) for l in session.listeners}
        self.sidebar.update_card(session, session.listeners, labels, self._health)
        if session is self.manager.active:
            self.header.set_session(session)
        self.tabs.sync(self.manager.sessions, self.manager.active)
        counts = {state: sum(s.state == state for s in self.manager.sessions) for state in ("starting", "ready", "running", "failed")}
        self.sidebar.status.setText(" · ".join(f"{n} {state}" for state, n in counts.items() if n) or "No active terminals")

    def refresh_navigation(self):
        self.sidebar.sync_order(self.manager.sessions)
        self.tabs.sync(self.manager.sessions, self.manager.active)

    def set_mode(self, mode):
        self.config.view_mode = mode
        self.sidebar.scroll.setVisible(mode == "sidebar")
        self.tabs.setVisible(mode == "tabs")
        self.save_config()

    def rename(self, sid):
        session = self.session(sid)
        if not session:
            return
        name, accepted = QInputDialog.getText(self, "Rename terminal", "Name", text=session.name)
        if accepted and name.strip():
            session.name = name.strip()[:120]
            self.refresh_session(session)

    def move(self, sid, offset):
        identifiers = [s.id for s in self.manager.sessions]
        index = identifiers.index(sid)
        target = index + offset
        if 0 <= target < len(identifiers):
            identifiers[index], identifiers[target] = identifiers[target], identifiers[index]
            self.manager.reorder(identifiers)

    def cycle(self, offset):
        if self.manager.sessions:
            index = self.manager.sessions.index(self.manager.active) if self.manager.active in self.manager.sessions else 0
            self.manager.set_active(self.manager.sessions[(index + offset) % len(self.manager.sessions)])

    def retry(self, sid):
        session = self.session(sid)
        if session and session.state in ("failed", "exited"):
            self.statusBar().showMessage("Closing failed launch before retry…")
            session.prepare_close()
            self.work.submit(session.close, lambda _: self._retry_closed(session))

    def _retry_closed(self, session):
        from .session_manager import TerminalSession
        replacement = self.manager.create(session.shell, session.cwd, session.name, session.startup_cmd,
                                          session.distro, definition_id=session.definition_id,
                                          profile_id=session.profile_id, instance_id=session.instance_id,
                                          accent=session.accent, restart_cmd=session.restart_cmd)
        if session.view:
            self.stack.removeWidget(session.view)
            session.view.deleteLater()
        self.manager.close(session)
        self.manager.set_active(replacement)

    def profile_action(self, action, identifier):
        profile = next((p for p in self.config.profiles if p.id == identifier), None)
        if action in ("run", "copy", "missing"):
            if not profile:
                self.statusBar().showMessage("Select or create a workspace profile first")
                return
            if action == "run" and any(s.profile_id == profile.id for s in self.manager.sessions):
                self.manager.launch_profile(profile)
                self.statusBar().showMessage("Focused existing workspace. Use Restore missing terminals or Launch another copy explicitly.")
                return
            if action == "copy" and QMessageBox.question(self, "Launch another copy", "Another copy may conflict with running ports. Launch it?") != QMessageBox.StandardButton.Yes:
                return
            if profile.needs_review():
                commands = "\n\n".join(f"{t.name}\nShell: {t.shell} {t.distro}\nFolder: {t.cwd or '(home)'}\nStartup: {redact_cmdline(t.startup_cmd) or '(none)'}\nRestart: {redact_cmdline(t.restart_cmd) or '(startup command)'}" for t in profile.terminals)
                dialog = QDialog(self)
                dialog.setWindowTitle("Review workspace commands")
                dialog.resize(700, 440)
                layout = QVBoxLayout(dialog)
                text = QPlainTextEdit(commands)
                text.setReadOnly(True)
                layout.addWidget(text)
                controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
                controls.button(QDialogButtonBox.StandardButton.Ok).setText("Approve and run")
                controls.accepted.connect(dialog.accept); controls.rejected.connect(dialog.reject)
                layout.addWidget(controls)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                profile.approve()
                self.save_config()
            self.manager.launch_profile(profile, duplicate=action == "copy", missing=action == "missing")
            return
        if action == "delete" and profile:
            if QMessageBox.question(self, "Delete profile", f"Delete '{profile.name}'? Running terminals stay open.") == QMessageBox.StandardButton.Yes:
                self.config.profiles.remove(profile)
                self.save_config(); self.sidebar.set_profiles(self.config.profiles)
            return
        if action == "save":
            sessions = [s for s in self.manager.sessions if not self.manager.active or not self.manager.active.instance_id or s.instance_id == self.manager.active.instance_id]
            if not sessions:
                self.statusBar().showMessage("Open a terminal before saving a workspace"); return
            profile = WorkspaceProfile(name="Saved workspace", terminals=[TerminalProfile(name=s.name, shell=s.shell, cwd=s.current_cwd or s.cwd,
                distro=s.distro, startup_cmd=s.startup_cmd, restart_cmd=s.restart_cmd, accent=s.accent, expected_ports=s.expected_ports) for s in sessions])
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
        dialog = ProfileDialog(profile, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            edited = dialog.profile
            if original_id:
                index = next(i for i, p in enumerate(self.config.profiles) if p.id == original_id)
                edited.revision += 1
                self.config.profiles[index] = edited
            else:
                self.config.profiles.append(edited)
            self.save_config()
            self.sidebar.set_profiles(self.config.profiles)
            self.sidebar.profile_combo.setCurrentIndex(self.sidebar.profile_combo.findData(edited.id))

    def poll(self):
        if self._polling or self._closing:
            return
        self._polling = True
        sessions = tuple(self.manager.sessions)
        self.work.submit(lambda: collect_snapshot(sessions), self._snapshot, self._snapshot_error)

    def _snapshot_error(self, error):
        self._polling = False
        self.statusBar().showMessage(f"Port data stale: {error}")

    def _snapshot(self, result):
        self._polling = False
        attributed, external, children, errors = result
        self._external = external
        self._all_listeners = list(external)
        for session in self.manager.sessions:
            session.listeners = attributed.get(session.id, [])
            session.children = children.get(session.id, [])
            session.child_name = session.children[-1]["name"] if session.children else ""
            self.sidebar.set_listeners(session.id, session.listeners)
            self._all_listeners.extend(session.listeners)
            self.refresh_session(session)
        self.sidebar.update_external([l for l in external if filter_noise(l, self.config.process_denylist, self.config.process_allowlist)])
        if errors:
            self.statusBar().showMessage("Attribution warning: " + errors[0])
        self.run_probes()

    def url(self, sid, port):
        session = self.session(sid)
        listeners = session.listeners if session else self._all_listeners
        endpoint = next((l for l in listeners if l.port == port), None)
        host = "[::1]" if endpoint and ":" in endpoint.address else "localhost"
        return f"http://{host}:{port}"

    def open_port(self, sid, port):
        QDesktopServices.openUrl(QUrl(self.url(sid, port)))

    def copy_port(self, sid, port):
        QApplication.clipboard().setText(self.url(sid, port))
        self.statusBar().showMessage(f"Copied URL for :{port}", 2500)

    def find_port(self, port):
        # Refresh all environments, bypassing presentation filters.
        self.work.submit(lambda: collect_snapshot(tuple(self.manager.sessions)), lambda result: self._show_port(port, result), self._snapshot_error)

    def _show_port(self, port, result):
        attributed, external, _, _ = result
        listeners = [l for l in external + [l for group in attributed.values() for l in group] if l.port == port]
        if not listeners:
            QMessageBox.information(self, "Port search", f"No accessible localhost listener on :{port}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Owners of :{port}")
        layout = QVBoxLayout(dialog)
        for listener in listeners:
            owner = listener.owner
            label = QLabel(f"{listener.env} {listener.distro} · {listener.address}:{port} · {owner.name if owner else 'unknown'} · PID {owner.pid if owner else '?'}")
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
            layout.addWidget(button("Force kill this listener owner", "stop", lambda l=listener: self.kill_listener(l)))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        dialog.exec()

    def kill_listener(self, listener):
        owner = listener.owner
        if not owner:
            QMessageBox.warning(self, "Cannot kill", "Owner inaccessible; no process action available")
            return
        session_roots = {s.pty.pid for s in self.manager.sessions if s.pty}
        # The ConPTY root is a barrier bootstrap; its interactive shell is
        # protected too, even if that shell itself owns a listening socket.
        for s in self.manager.sessions:
            session_roots.update(p["pid"] for p in s.children if p.get("name", "").lower() in ("powershell.exe", "pwsh.exe", "cmd.exe"))
        protected = session_roots
        text = f"Force termination affects every listener owned by this process.\n\nEnvironment: {owner.env} {owner.distro}\nPID: {owner.pid}\nProcess: {owner.name}\nEndpoint: {listener.address}:{listener.port}\nStart identity: {owner.create_time}\n\nParent shell is protected. A watcher may restart this process."
        question = QMessageBox(self)
        question.setWindowTitle("Confirm process termination")
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setText(text)
        question.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if question.exec() != QMessageBox.StandardButton.Yes:
            return
        if owner.env == "wsl":
            session = next((s for s in self.manager.sessions if s.distro == owner.distro and s.wsl), None)
            if not session:
                return
            def signal_work():
                return session.wsl.send_signal(owner.pid, 15, start=owner.create_time,
                                               address=listener.address, port=listener.port)
            self.work.submit(signal_work, lambda value: self.statusBar().showMessage(str(value)), lambda error: QMessageBox.warning(self, "Signal refused", error))
        else:
            def kill_work():
                return kill_windows(owner, port=listener.port, address=listener.address, protected_pids=protected)
            self.work.submit(kill_work, lambda result: self.statusBar().showMessage(result.message), lambda error: QMessageBox.warning(self, "Kill failed", error))

    def kill_active(self):
        session = self.manager.active
        if not session or not session.listeners:
            return
        listeners = session.listeners
        items = [f"{l.address}:{l.port} · {l.owner.name if l.owner else 'unknown'}" for l in listeners]
        choice, accepted = QInputDialog.getItem(self, "Choose listener", "Process to terminate", items, 0, False)
        if accepted:
            self.kill_listener(listeners[items.index(choice)])

    def restart(self):
        session = self.manager.active
        if not session:
            return
        if session.shell == "cmd":
            session.send_ctrl_c()
            if QMessageBox.question(self, "Confirm CMD prompt", "Has the foreground command stopped and CMD returned to its prompt? Run the saved restart command now?") == QMessageBox.StandardButton.Yes:
                session.restart(confirmed=True)
        else:
            session.restart()

    def edit_label(self, sid, port):
        session = self.session(sid)
        if not session:
            return
        label, ok = QInputDialog.getText(self, "Port label", f"Label for :{port}", text=self.config.get_label(session.label_scope, port))
        if ok:
            self.config.set_label(session.label_scope, port, label)
            self.save_config(); self.refresh_session(session)

    def toggle_probe(self, sid, port, enabled):
        key = sid, port
        if enabled:
            self._probe_enabled.add(key)
        else:
            self._probe_enabled.discard(key)
            self._health.pop(key, None)
        self.run_probes()

    def run_probes(self):
        for sid, port in tuple(self._probe_enabled):
            session = self.session(sid)
            if not session or not any(l.port == port for l in session.listeners):
                continue
            if time.monotonic() - self._probe_last.get((sid, port), 0) >= 5:
                self._probe_last[(sid, port)] = time.monotonic()
                endpoint = next(l for l in session.listeners if l.port == port)
                self.probes.request(f"{sid}:{port}", port, host="::1" if ":" in endpoint.address else "127.0.0.1")

    def _probe_result(self, key, result):
        sid, port = key.rsplit(":", 1)
        session = self.session(sid)
        if session:
            self._health[(sid, int(port))] = result.label
            self.refresh_session(session)

    def close_session(self, session):
        if not session or session.state == "stopping":
            return
        if session.state not in ("exited", "failed") and QMessageBox.question(self, "Close terminal", f"Close '{session.name}' and stop its owned processes?") != QMessageBox.StandardButton.Yes:
            return
        session.state = "stopping"
        session.prepare_close()
        self.refresh_session(session)
        self.work.submit(session.close, lambda _: self._closed_session(session))

    def _closed_session(self, session):
        self.stack.removeWidget(session.view)
        session.view.deleteLater()
        self.manager.close(session)

    def settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferences")
        layout = QFormLayout(dialog)
        deny = QPlainTextEdit("\n".join(self.config.process_denylist))
        allow = QPlainTextEdit("\n".join(self.config.process_allowlist))
        deny.setMaximumHeight(100); allow.setMaximumHeight(80)
        layout.addRow("External process denylist", deny)
        layout.addRow("External process allowlist", allow)
        motion = QComboBox()
        for text, value in [("Follow Windows", "system"), ("Reduce motion", "on"), ("Enable motion", "off")]:
            motion.addItem(text, value)
        motion.setCurrentIndex(max(0, motion.findData(self.config.reduced_motion)))
        layout.addRow("Motion", motion)
        recover = QCheckBox("Back up unreadable config and enable recovery save")
        recover.setVisible(self.config.read_only)
        layout.addRow(recover)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dialog.accept); controls.rejected.connect(dialog.reject)
        layout.addRow(controls)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.config.read_only and recover.isChecked():
                config_store.recover(self.config)
            self.config.process_denylist = [s.strip().lower() for s in deny.toPlainText().splitlines() if s.strip()][:256]
            self.config.process_allowlist = [s.strip().lower() for s in allow.toPlainText().splitlines() if s.strip()][:256]
            self.config.reduced_motion = motion.currentData()
            self.save_config(); self._motion()

    def closeEvent(self, event):
        if self._approved_close:
            event.accept()
            return
        event.ignore()
        if self._closing:
            return
        if self.manager.sessions and QMessageBox.question(self, "Quit Ports", "Quit and stop all Ports-owned terminal sessions? External processes remain untouched.") != QMessageBox.StandardButton.Yes:
            return
        self.config.saved_sessions = [s.to_saved() for s in self.manager.sessions]
        self.config.geometry = base64.b64encode(bytes(self.saveGeometry())).decode()
        self.config.splitter = base64.b64encode(bytes(self.splitter.saveState())).decode()
        self.save_config()
        self.timer.stop()
        self.probes.close()
        sessions = tuple(self.manager.sessions)
        for session in sessions:
            session.prepare_close()
        self.statusBar().showMessage("Stopping terminal sessions…")
        self.setEnabled(False)
        self._closing = True
        # Cleanup callbacks need delivery even while ordinary callbacks ignored.
        def cleanup():
            for session in sessions:
                session.close()
            return True
        self._cleanup_callback = self._finish_close
        self.work.submit(cleanup, self._finish_close, self._finish_close)

    def _finish_close(self, _):
        self._approved_close = True
        self.work.close()
        self.close()
