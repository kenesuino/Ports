"""Capture the rail in its polished state for visual review."""
import os
import tempfile

os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-rail-shot-')
os.environ['APPDATA'] = _temp.name

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.__main__ import _dark_palette
from ports.main_window import MainWindow
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.theme import QSS

app = QApplication(['ports-rail-shot']); app.setStyle('Fusion')
app.setPalette(_dark_palette()); app.setStyleSheet(QSS)
window = MainWindow(); window.timer.stop(); window.age_timer.stop()
window.resize(1280, 800); window.show()
profile = WorkspaceProfile(name='Frontend', terminals=[TerminalProfile(name='Dev server'), TerminalProfile(name='Worker')])
other = WorkspaceProfile(name='Backend', terminals=[TerminalProfile(name='API')])
window.config.profiles = [profile, other]
window.sidebar.set_profiles([profile, other])
window.load_workspace(profile.id)
root = __import__('pathlib').Path(__file__).resolve().parents[1] / 'artifacts'
root.mkdir(exist_ok=True)


def capture():
    window.grab().save(str(root / 'rail-polished-1280.png'))
    window.sidebar.grab().save(str(root / 'rail-only.png'))
    window.timer.stop(); window.age_timer.stop(); window.probes.close(); window.work.close()
    window._approved_close = True; window.close(); app.exit(0)


QTimer.singleShot(1200, capture)
raise SystemExit(app.exec())
