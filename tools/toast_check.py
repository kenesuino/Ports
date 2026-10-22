"""Confirm the toast is actually visible when a port appears, then dismisses."""

from __future__ import annotations

import json
import os
import tempfile

os.environ.pop("QT_QPA_PLATFORM", None)
_temporary = tempfile.TemporaryDirectory(prefix="ports-toast-")
os.environ["APPDATA"] = _temporary.name

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from ports.main_window import MainWindow
from ports.theme import QSS

app = QApplication(["ports-toast-check"])
app.setStyleSheet(QSS)
window = MainWindow()
window.resize(1000, 700)
window.show()

report: dict = {}


def fire() -> None:
    report["before"] = window.toast.isVisible()
    window._notify_port_changes({("abc", 3000)}, set())
    report["immediately_after"] = window.toast.isVisible()
    report["text"] = window.toast.label.text()
    report["geometry_ok"] = window.toast.x() > 0 and window.toast.y() > 0
    QTimer.singleShot(3200, after_timeout)


def after_timeout() -> None:
    report["after_autodismiss"] = window.toast.isVisible()
    print(json.dumps(report, indent=2), flush=True)
    window.timer.stop()
    window.probes.close()
    window.work.close()
    window._approved_close = True
    window.close()
    ok = (not report["before"] and report["immediately_after"]
          and report["text"] and report["geometry_ok"]
          and not report["after_autodismiss"])
    app.exit(0 if ok else 1)


QTimer.singleShot(2000, fire)
QTimer.singleShot(15000, lambda: app.exit(3))
raise SystemExit(app.exec())
