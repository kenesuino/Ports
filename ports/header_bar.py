"""Single-row workspace header: title, path, status, port chips, actions."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from .icons import icon
from .widgets import ElidedLabel
from .motion import StatusDot
from .theme import (
    DESTRUCTIVE, FONT_BODY, FONT_TITLE, MONO_FONT, SPACE_2, SPACE_3, TEXT_MUTED,
)


def elide_middle(text: str, parts: int = 2) -> str:
    """Collapse a filesystem path to its last two segments."""
    cleaned = text.replace("\\", "/").rstrip("/")
    segments = [s for s in cleaned.split("/") if s]
    if not segments:
        return text
    if len(segments) <= parts:
        return "/".join(segments)
    return "…/" + "/".join(segments[-parts:])


class TooltipButton(QPushButton):
    """Button whose tooltip also appears while disabled.

    Qt suppresses tooltips on disabled widgets, which would hide the reason a
    control is unavailable. This keeps hover events enabled so the explanation
    is always discoverable.
    """

    def __init__(self, label: str, tip: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._default_tip = tip
        self.setAccessibleName(label)
        self.setAccessibleDescription(tip)
        self.setToolTip(f"{label} — {tip}")
        self._sync_hover()

    def set_tip(self, detail: str) -> None:
        self.setToolTip(f"{self._label} — {detail}")
        self.setAccessibleDescription(detail)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 - Qt casing
        super().setEnabled(enabled)
        self._sync_hover()

    def _sync_hover(self) -> None:
        # Qt drops hover events for disabled widgets; re-enable them so the
        # tooltip still explains the disabled state.
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)


class StatusPopover(QMenu):
    """Process/listener detail for the active session, shown on pill click."""

    killRequested = pyqtSignal(object)

    def populate(self, session) -> None:
        self.clear()
        if session is None:
            self.addAction("No active session").setEnabled(False)
            return
        header = self.addAction(f"{session.name} · {session.state}")
        header.setEnabled(False)
        self.addSeparator()
        folder = session.current_cwd or session.cwd or "shell home"
        path_action = self.addAction(f"Folder: {elide_middle(folder, 3)}")
        path_action.setEnabled(False)
        if session.children:
            self.addSeparator()
            roots = self.addAction("Processes")
            roots.setEnabled(False)
            for item in session.children[:8]:
                label = f"  {item['name']}  ·  PID {item['pid']}"
                self.addAction(label).setEnabled(False)
        self.addSeparator()
        if not session.listeners:
            self.addAction("No listening ports").setEnabled(False)
        for listener in session.listeners:
            owner = listener.owner.name if listener.owner else "unknown"
            action = self.addAction(
                f":{listener.port}  ·  {owner}  ·  {listener.address}")
            action.triggered.connect(
                lambda _=False, l=listener: self.killRequested.emit(l))


class HeaderBar(QWidget):
    restartRequested = pyqtSignal()
    ctrlCRequested = pyqtSignal()
    killPortRequested = pyqtSignal()
    clearRequested = pyqtSignal()
    copyPathRequested = pyqtSignal()
    openFolderRequested = pyqtSignal()
    openPortRequested = pyqtSignal(int)
    portMenuRequested = pyqtSignal(int, object)
    killListenerRequested = pyqtSignal(object)
    panelToggleRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("header")
        self.setFixedHeight(48)
        self._session = None
        self._chips: dict[int, QPushButton] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE_3, 0, SPACE_3, 0)
        row.setSpacing(SPACE_2)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        self.title = ElidedLabel("Ports", self)
        self.title.setStyleSheet(FONT_TITLE)
        self.path = ElidedLabel("No session", self)
        self.path.setStyleSheet(
            f"color:{TEXT_MUTED}; font-family:{MONO_FONT}; {FONT_BODY}")
        left.addWidget(self.title)
        left.addWidget(self.path)
        row.addLayout(left, 1)

        self.copy_btn = self._icon_button("copy", "Copy folder path",
                                          self.copyPathRequested.emit)
        self.open_btn = self._icon_button("open-folder", "Open folder",
                                          self.openFolderRequested.emit)
        row.addWidget(self.copy_btn)
        row.addWidget(self.open_btn)

        self.status = QPushButton()
        self.status.setObjectName("statusPill")
        self.status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status.setAccessibleName("Session status and listeners")
        self.status.clicked.connect(self._show_popover)
        self.popover = StatusPopover(self)
        self.popover.killRequested.connect(self.killListenerRequested)
        row.addWidget(self.status)

        self.dot = StatusDot(self)
        row.addWidget(self.dot)

        self.chip_row = QHBoxLayout()
        self.chip_row.setContentsMargins(0, 0, 0, 0)
        self.chip_row.setSpacing(SPACE_2)
        row.addLayout(self.chip_row)

        self.restart_btn = self._action_button(
            "restart", "Restart saved command", "Re-run the saved command",
            self.restartRequested.emit)
        self.ctrlc_btn = self._action_button(
            "stop", "Interrupt", "Send Ctrl+C to the running command",
            self.ctrlCRequested.emit)
        self.kill_btn = self._action_button(
            "kill", "Kill listener", "Terminate the process holding the selected port",
            self.killPortRequested.emit, danger=True)
        self.clear_btn = self._action_button(
            "clear", "Clear scrollback", "Keep the process running",
            self.clearRequested.emit)
        for control in (self.restart_btn, self.ctrlc_btn, self.kill_btn,
                        self.clear_btn):
            row.addWidget(control)
        self.panel_button = self._icon_button('layout', 'Show or hide ports inspector (Ctrl+Shift+E)', self.panelToggleRequested.emit)
        self.panel_button.setCheckable(True)
        self.panel_button.setFixedSize(30, 30)
        row.addWidget(self.panel_button)
        self.panel_button.show()

        self._set_enabled(False)

    def _action_button(self, glyph: str, label: str, tip: str,
                       callback, danger: bool = False) -> QPushButton:
        button = TooltipButton(label, tip)
        button.setObjectName("danger" if danger else "iconBtn")
        button.setIcon(icon(glyph, DESTRUCTIVE if danger else None))
        button.setFixedSize(30, 30)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def _icon_button(self, glyph: str, tip: str, callback):
        button = QPushButton()
        button.setObjectName("iconBtn")
        button.setIcon(icon(glyph))
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.clicked.connect(callback)
        button.setVisible(False)
        return button

    def _set_enabled(self, enabled: bool) -> None:
        for control in (self.restart_btn, self.ctrlc_btn, self.kill_btn,
                        self.clear_btn, self.status):
            control.setEnabled(enabled)
        for control in (self.copy_btn, self.open_btn):
            control.setVisible(enabled)

    def _show_popover(self) -> None:
        self.popover.populate(self._session)
        origin = self.status.mapToGlobal(
            QPoint(0, self.status.height() + 4))
        self.popover.popup(origin)

    def _build_chip(self, text: str, port: int, ghost: bool) -> QPushButton:
        chip = QPushButton(text)
        chip.setObjectName("ghostChip" if ghost else "chip")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(
            f"Expected :{port} is not listening yet" if ghost
            else f"Open http://localhost:{port}")
        if not ghost:
            chip.clicked.connect(lambda: self.openPortRequested.emit(port))
        chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        chip.customContextMenuRequested.connect(
            lambda pos, p=port, c=chip: self.portMenuRequested.emit(
                p, c.mapToGlobal(pos)))
        return chip

    def set_session(self, session) -> None:
        self._session = session
        if session is None:
            self.title.setText("Ports")
            self.path.setText("No session")
            self.path.setToolTip("")
            self._set_enabled(False)
            self.status.setText("Stopped · 0 ports")
            self.dot.set_state("idle")
            self._sync_chips(None)
            return

        self._set_enabled(True)
        self.title.setText(session.name)
        folder = session.current_cwd or session.cwd or "shell home"
        label = "Folder" if session.current_cwd else "Starting folder"
        self.path.setText(f"{label}: {elide_middle(folder)}")
        self.path.setToolTip(folder)
        self.copy_btn.setEnabled(bool(session.current_cwd or session.cwd))
        self.open_btn.setEnabled(bool(session.current_cwd or session.cwd))
        self.restart_btn.setEnabled(session.can_restart())
        reason = session.restart_reason()
        self.restart_btn.set_tip(
            f"unavailable — {reason}" if reason
            else f"re-run: {session.restart_cmd}")
        self.kill_btn.setEnabled(bool(session.listeners))
        self.kill_btn.set_tip(
            "terminate the process holding the selected port" if session.listeners
            else "no listening port")
        self._sync_chips(session)

    def _sync_chips(self, session) -> None:
        ports = {l.port for l in session.listeners} if session else set()
        expected = set(session.expected_ports) if session else set()
        wanted = ports | expected
        for port in list(self._chips):
            if port not in wanted:
                self._chips.pop(port).deleteLater()
        for port in sorted(wanted):
            if port not in self._chips:
                ghost = port not in ports
                chip = self._build_chip(
                    f":{port}", port, ghost)
                self._chips[port] = chip
                self.chip_row.addWidget(chip)
        for port, chip in self._chips.items():
            ghost = port not in ports
            name = "ghostChip" if ghost else "chip"
            if chip.objectName() != name:
                chip.setObjectName(name)
                chip.style().unpolish(chip)
                chip.style().polish(chip)
            chip.setToolTip(
                f"Expected :{port} is not listening yet" if ghost
                else f"Open http://localhost:{port}")

        listening = len(ports)
        if session is None:
            text, state = "Stopped · 0 ports", "idle"
        elif session.state in ("failed", "exited"):
            text, state = f"{session.state.title()} · {listening} ports", "failed"
        elif session.state in ("starting", "stopping") or (
                expected - ports):
            waiting = sorted(expected - ports)
            detail = f":{waiting[0]}" if waiting else session.state
            text, state = f"Waiting · {detail}", "waiting"
        elif listening:
            text, state = f"Listening · {listening} ports", "listening"
        else:
            text, state = "Ready · 0 ports", "ready"
        self.status.setText(text)
        self.dot.set_state(state)
