"""Main window: layout, port monitor loop, dialogs, wiring."""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
    QMessageBox, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from . import config_store
from .header_bar import HeaderBar
from .http_probe import ProbePool
from .port_monitor import (
    Listener, OwnerIdentity, collect_windows_listeners, filter_noise,
    map_ports, merge_wsl_forwarders,
)
from .process_control import (
    current_owner_of_port, describe_target, kill_windows,
)
from .pty_session import SHELLS
from .session_manager import SessionManager, TerminalSession
from .sidebar import Sidebar
from .theme import COLOR_HTTP_FAIL, COLOR_HTTP_OK, COLOR_UNCHECKED


class KillConfirmDialog(QDialog):
    """Destructive-action gate: shows identity before any kill."""

    def __init__(self, listener: Listener, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm kill")
        layout = QVBoxLayout(self)
        owner = listener.owner
        if owner and owner.env == "windows":
            info = describe_target(owner)
            name, pid = info["name"], info["pid"]
            cmdline = info["cmdline"]
        elif owner:
            name, pid = owner.name, owner.pid
            cmdline = ""
        else:
            name, pid, cmdline = "unknown", "?", ""
        env = f"wsl:{owner.distro}" if owner and owner.env == "wsl" \
            else "windows"
        text = QLabel(
            f"Kill process holding port <b>:{listener.port}</b>?<br><br>"
            f"<b>PID:</b> {pid}<br><b>Name:</b> {name}<br>"
            f"<b>Env:</b> {env}<br>"
            + (f"<b>Command:</b> {cmdline}<br>" if cmdline else "")
            + "<br>Parent shell stays alive. Watchers may restart the "
              "listener.")
        text.setWordWrap(True)
        layout.addWidget(text)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kill")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName(
            "danger")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ports")
        self.resize(1280, 800)

        self.config = config_store.load()
        self.manager = SessionManager(self)
        self._probe_pool = ProbePool(self._on_probe_result)
        self._probe_enabled: set[tuple[str, int]] = set()
        self._probe_last: dict[tuple[str, int], float] = {}
        self._health: dict[tuple[str, int], str] = {}

        splitter = QSplitter()
        self.sidebar = Sidebar()
        splitter.addWidget(self.sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.header = HeaderBar()
        right_layout.addWidget(self.header)
        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 980])
        self.setCentralWidget(splitter)

        self._wire()
        self.header.set_session(None)

        self._monitor = QTimer(self)
        self._monitor.setInterval(1500)
        self._monitor.timeout.connect(self._poll_ports)
        self._monitor.start()

        self._offer_restore()

    # -- wiring ---------------------------------------------------------

    def _wire(self):
        sb = self.sidebar
        sb.newSessionRequested.connect(self._create_session)
        sb.sessionSelected.connect(self.manager.set_active)
        sb.sessionCloseRequested.connect(self._close_session)
        sb.findPort.connect(self._find_port)
        sb.openUrl.connect(self._open_port)
        sb.killRequested.connect(self._kill_listener)
        sb.labelEditRequested.connect(self._edit_label)
        sb.probeToggled.connect(self._toggle_probe)

        self.manager.sessionAdded.connect(self._on_session_added)
        self.manager.sessionRemoved.connect(self._on_session_removed)
        self.manager.activeChanged.connect(self._on_active_changed)

        self.header.restartRequested.connect(
            lambda: self.manager.active and self.manager.active.restart())
        self.header.ctrlCRequested.connect(
            lambda: self.manager.active and self.manager.active.send_ctrl_c())
        self.header.killPortRequested.connect(self._kill_active_port)
        self.header.clearRequested.connect(
            lambda: self.manager.active and self.manager.active.clear())
        self.header.searchRequested.connect(self._search_terminal)

    # -- sessions ---------------------------------------------------------

    def _create_session(self, values: dict):
        import os
        cwd = values["cwd"]
        if cwd and not os.path.isdir(cwd):
            QMessageBox.warning(self, "Ports", f"Folder not found:\n{cwd}")
            return
        self.manager.create(values["shell"], cwd, values["name"],
                            values["startup_cmd"], values["distro"],
                            self.config.scrollback_lines)

    def _on_session_added(self, session: TerminalSession):
        session.start(self.config.scrollback_lines)
        self.stack.addWidget(session.view)
        self.sidebar.add_session(session)
        session.changed.connect(
            lambda s=session: self._refresh_session(s))

    def _on_session_removed(self, session_id: str):
        # view already removed in _close_session
        pass

    def _close_session(self, session: TerminalSession):
        infos = session.descendant_infos()
        if infos:
            names = ", ".join(sorted({i['name'] for i in infos})[:4])
            ans = QMessageBox.question(
                self, "Ports",
                f"Close '{session.name}'? Running processes will be killed:"
                f"\n{names}")
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.stack.removeWidget(session.view)
        self.sidebar.remove_session(session.id)
        self.manager.close(session)

    def _on_active_changed(self, session):
        self.sidebar.set_active(session)
        self.header.set_session(session)
        if session and session.view:
            self.stack.setCurrentWidget(session.view)
            session.view.refit()
            session.view.focus_terminal()

    def _refresh_session(self, session):
        if session is self.manager.active:
            self.header.set_session(session)

    # -- port monitoring ---------------------------------------------------

    def _poll_ports(self):
        windows = collect_windows_listeners()
        session_members = {}
        session_roots = {}
        wsl_ports: dict[str, list[Listener]] = {}
        for s in self.manager.sessions:
            if not s.pty or not s.pty.pid:
                continue
            if s.shell == "wsl":
                if s.wsl:
                    lst = [
                        Listener(l.address, l.port,
                                 OwnerIdentity("wsl", l.pid or 0, l.start,
                                               l.name, s.distro),
                                 env="wsl", distro=s.distro)
                        for l in s.wsl.listeners() if l.session_owned
                    ]
                    wsl_ports[s.id] = lst
            else:
                session_members[s.id] = s.pty.descendant_pids()
                session_roots[s.id] = s.pty.pid

        windows = merge_wsl_forwarders(windows, wsl_ports)
        attributed, external = map_ports(session_members, windows,
                                         session_roots)
        for sid, lst in wsl_ports.items():
            attributed.setdefault(sid, []).extend(lst)

        labels = {}
        for s in self.manager.sessions:
            lst = attributed.get(s.id, [])
            self.sidebar.set_listeners(s.id, lst)
            for l in lst:
                lbl = self.config.get_label(s.id, l.port)
                if lbl:
                    labels[(s.id, l.port)] = lbl
            self.sidebar.update_card(s, lst, labels)
            if s is self.manager.active:
                self.header.set_child(s.active_child_name())
                self.header.kill_btn.setEnabled(bool(lst))

        kept = [l for l in external
                if filter_noise(l, self.config.process_denylist,
                                self.config.process_allowlist)]
        self.sidebar.update_external(kept)
        self._run_due_probes(attributed)

    # -- find / open / kill ---------------------------------------------

    def _open_port(self, session_id: str, port: int):
        import webbrowser
        webbrowser.open(f"http://localhost:{port}")

    def _find_port(self, port: int):
        owner = current_owner_of_port(port)
        if not owner:
            QMessageBox.information(self, "Ports",
                                    f"No localhost listener on :{port}")
            return
        lst = Listener("127.0.0.1", port, owner)
        self._kill_listener(lst)

    def _kill_listener(self, listener: Listener):
        dlg = KillConfirmDialog(listener, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        owner = listener.owner
        if not owner:
            QMessageBox.warning(self, "Ports", "Owner unknown; cannot kill.")
            return
        if owner.env == "wsl":
            session = next((s for s in self.manager.sessions
                            if s.shell == "wsl" and s.distro == owner.distro),
                           None)
            if not session or not session.wsl:
                QMessageBox.warning(self, "Ports",
                                    "WSL helper not running for this distro.")
                return
            session.wsl.send_signal(owner.pid, 15)
            return
        result = kill_windows(owner)
        if not result.ok:
            QMessageBox.warning(self, "Ports", result.message)

    def _kill_active_port(self):
        s = self.manager.active
        if not s:
            return
        listeners = self.sidebar._listeners_for(s.id)
        if not listeners:
            return
        if len(listeners) == 1:
            self._kill_listener(listeners[0])
            return
        items = [f":{l.port} ({l.owner.name if l.owner else '?'})"
                 for l in listeners]
        choice, ok = QInputDialog.getItem(
            self, "Ports", "Kill which port process?", items, 0, False)
        if ok:
            self._kill_listener(listeners[items.index(choice)])

    # -- labels / probes ------------------------------------------------

    def _edit_label(self, session_id: str, port: int):
        current = self.config.get_label(session_id, port)
        text, ok = QInputDialog.getText(
            self, "Ports", f"Label for :{port} (empty clears):", text=current)
        if ok:
            self.config.set_label(session_id, port, text)
            config_store.save(self.config)

    def _toggle_probe(self, session_id: str, port: int, on: bool):
        key = (session_id, port)
        if on:
            self._probe_enabled.add(key)
        else:
            self._probe_enabled.discard(key)
            self._health.pop(key, None)

    def _run_due_probes(self, attributed):
        import time
        now = time.time()
        for (sid, port) in list(self._probe_enabled):
            if port not in [l.port for l in attributed.get(sid, [])]:
                continue
            if now - self._probe_last.get((sid, port), 0) < 5.0:
                continue
            self._probe_last[(sid, port)] = now
            self._probe_pool.request(f"{sid}:{port}", port)

    def _on_probe_result(self, key: str, result):
        sid, port_s = key.rsplit(":", 1)
        color = COLOR_HTTP_OK if result.state == "responding" \
            else COLOR_HTTP_FAIL if result.state in ("refused",) \
            else COLOR_UNCHECKED
        self._health[(sid, int(port_s))] = result.label
        # color applied on next monitor pass via tooltip/health map
        card = self.sidebar._cards.get(sid)
        if card:
            for i in range(card.badges.count()):
                w = card.badges.itemAt(i).widget()
                if w and w.text().startswith(f":{port_s}"):
                    w.set_health(color)
                    w.setToolTip(f"{w.toolTip().split(chr(10))[0]}\n"
                                 f"{result.label}")

    # -- misc -----------------------------------------------------------

    def _search_terminal(self, needle: str):
        s = self.manager.active
        if s and s.view and needle:
            s.view.search(needle)

    def _offer_restore(self):
        if not self.config.saved_sessions:
            return
        ans = QMessageBox.question(
            self, "Ports",
            f"Restore {len(self.config.saved_sessions)} previous session(s)?"
            "\nFresh shells are started; startup commands are not re-run "
            "automatically.")
        if ans != QMessageBox.StandardButton.Yes:
            return
        for saved in self.config.saved_sessions:
            s = self.manager.create(saved.shell, saved.cwd, saved.name,
                                    "", saved.distro,
                                    self.config.scrollback_lines)
            s.restart_cmd = saved.startup_cmd  # restore restart definition

    def closeEvent(self, event: QCloseEvent):
        busy = [s for s in self.manager.sessions if s.descendant_infos()]
        if busy:
            names = ", ".join(s.name for s in busy[:5])
            ans = QMessageBox.question(
                self, "Ports",
                f"Sessions with running processes: {names}\nQuit and kill "
                "them?")
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.config.saved_sessions = [s.to_saved()
                                      for s in self.manager.sessions]
        config_store.save(self.config)
        self._probe_pool.close()
        self.manager.shutdown()
        event.accept()
