"""End-to-end behavioral check: a real server in a tab produces a port toast.

Uses an isolated config directory so the user's real state is untouched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.pop("QT_QPA_PLATFORM", None)
_temporary = tempfile.TemporaryDirectory(prefix="ports-e2e-")
os.environ["APPDATA"] = _temporary.name

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from ports.main_window import MainWindow
from ports.theme import QSS

app = QApplication(["ports-e2e-check"])
app.setStyleSheet(QSS)
window = MainWindow()
window.resize(1280, 800)
window.show()

PORT = 54913
session = window.manager.create("cmd", name="Server")
report: dict = {}


def start_server() -> None:
    if session.pty is None:
        QTimer.singleShot(500, start_server)
        return
    session.pty.write(
        f'start "" /min "{sys.executable}" -m http.server {PORT}\r')


def inspect() -> None:
    ports = sorted({item.port for item in session.listeners})
    report.update(
        session_state=session.state,
        listeners=[f"{i.address}:{i.port}" for i in session.listeners],
        tab_label=window.tabs.tabs.tabText(0),
        header_chips=[c.text() for c in window.header.findChildren(type(
            window.header.status)) if c.objectName() == "chip"],
        rail_rows=len(window.inspector.ports_list._rows),
        toast_visible=window.toast.isVisible(),
        toast_text=window.toast.label.text(),
        footer_ports=window.footer_ports.text(),
        header_status=window.header.status.text(),
    )
    report["ok"] = PORT in ports and bool(report["toast_text"])
    print(json.dumps(report, indent=2), flush=True)
    session.state = "stopping"
    session.prepare_close()
    window.timer.stop()
    window.probes.close()
    session.close()
    window.work.close()
    window._approved_close = True
    window.close()
    app.exit(0 if report["ok"] else 1)


QTimer.singleShot(3000, start_server)
QTimer.singleShot(14000, inspect)
QTimer.singleShot(30000, lambda: app.exit(3))
raise SystemExit(app.exec())
