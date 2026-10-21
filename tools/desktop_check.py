"""Real WebEngine acceptance, isolated config, no user's running work touched."""
import argparse
import json
import os
from pathlib import Path
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--scale", default="1")
parser.add_argument("--width", type=int, default=1280)
args = parser.parse_args()
os.environ["QT_SCALE_FACTOR"] = args.scale
os.environ.pop("QT_QPA_PLATFORM", None)
config = tempfile.TemporaryDirectory(prefix="ports-ui-")
os.environ["APPDATA"] = config.name

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.main_window import MainWindow
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.theme import QSS
from ports.pty_session import available_shells

app = QApplication(["ports-desktop-check"])
app.setStyleSheet(QSS)
window = MainWindow()
window.resize(args.width, 800 if args.width >= 1280 else 700)
window.show()
profile = WorkspaceProfile(name="Local development", terminals=[
    TerminalProfile(name="Frontend", shell="pwsh" if "pwsh" in available_shells() else "powershell", startup_cmd="Write-Output PORTS_RENDER_OK", accent="#7aa2f7", expected_ports=[5173]),
    TerminalProfile(name="API · integration", shell="powershell", accent="#9ece6a"),
    TerminalProfile(name="Worker", shell="cmd", accent="#bb9af7"),
])
profile.approve()
window.config.profiles.append(profile)
window.sidebar.set_profiles(window.config.profiles)
window.sidebar.profile_combo.setCurrentIndex(1)
window.manager.launch_profile(profile)
root = Path(__file__).resolve().parents[1] / "artifacts"
root.mkdir(exist_ok=True)
status = {"rendered": False}


def check():
    session = window.manager.sessions[0]
    expression = "typeof window.portsBufferText === 'function' ? window.portsBufferText() : 'NO_BRIDGE'"
    def received(text):
        status.update(text=text, states=[s.state for s in window.manager.sessions],
                      ready=getattr(session.view, "_ready", False),
                      errors=[s.last_error for s in window.manager.sessions])
        status["rendered"] = isinstance(text, str) and "PORTS_RENDER_OK" in text
        window.manager.set_active(session)
        QTimer.singleShot(400, capture_sidebar)
    session.view.page().runJavaScript(expression, received)


def capture_sidebar():
    window.grab().save(str(root / f"sidebar-{args.width}-{args.scale}.png"))
    window.header.mode.setCurrentIndex(1)
    QTimer.singleShot(600, capture_tabs)


def capture_tabs():
    window.grab().save(str(root / f"tabs-{args.width}-{args.scale}.png"))
    (root / f"desktop-{args.width}-{args.scale}.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status), flush=True)
    window.timer.stop()
    window.probes.close()
    for session in window.manager.sessions:
        session.close()
    window.work.close()
    window._approved_close = True
    window.close()
    app.exit(0 if status["rendered"] else 1)

QTimer.singleShot(12000, check)
QTimer.singleShot(25000, lambda: app.exit(3))
raise SystemExit(app.exec())
