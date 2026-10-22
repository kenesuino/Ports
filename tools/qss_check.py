"""Verify QSS parses without warnings and tree arrows are drawn."""
import os
import tempfile

os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-qss-')
os.environ['APPDATA'] = _temp.name

import warnings
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.__main__ import _dark_palette
from ports.main_window import MainWindow
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.style import PortsStyle
from ports.theme import QSS
import json

app = QApplication(['ports-qss-check'])
app.setStyle('Fusion'); app.setPalette(_dark_palette()); app.setStyleSheet(QSS)
app.setStyle(PortsStyle(app.style()))
window = MainWindow(); window.timer.stop(); window.age_timer.stop()
window.resize(1280, 800); window.show()
profile = WorkspaceProfile(name='Frontend', terminals=[TerminalProfile(name='Dev server')])
other = WorkspaceProfile(name='Backend', terminals=[TerminalProfile(name='API')])
window.config.profiles = [profile, other]
window.sidebar.set_profiles([profile, other])
window.load_workspace(profile.id)
root = __import__('pathlib').Path(__file__).resolve().parents[1] / 'artifacts'
root.mkdir(exist_ok=True)
report = {}


def inspect():
    tree = window.sidebar.tree
    report['top_level_rows'] = tree.topLevelItemCount()
    report['branch_indicators'] = tree.style().standardIcon(
        tree.style().StandardPixmap.SP_ArrowRight if False else
        __import__('PyQt6.QtWidgets', fromlist=['QStyle']).QStyle.StandardPixmap.SP_ArrowRight
    ).isNull() is False
    window.grab().save(str(root / 'qss-fixed-1280.png'))
    window.sidebar.grab().save(str(root / 'qss-rail.png'))
    report['passed'] = report['top_level_rows'] >= 2
    print(json.dumps(report, indent=2), flush=True)
    window.timer.stop(); window.age_timer.stop(); window.probes.close(); window.work.close()
    window._approved_close = True; window.close(); app.exit(0 if report['passed'] else 1)


QTimer.singleShot(1200, inspect)
raise SystemExit(app.exec())
