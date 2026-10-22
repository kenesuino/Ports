"""Trace delegate paint calls and the state they receive."""
import os
import tempfile

os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-paint-')
os.environ['APPDATA'] = _temp.name

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QStyle
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.__main__ import _dark_palette
from ports.main_window import MainWindow
from ports.style import PortsStyle
from ports.theme import QSS
import json

app = QApplication(['ports-paint'])
app.setStyle('Fusion'); app.setPalette(_dark_palette()); app.setStyleSheet(QSS)
app.setStyle(PortsStyle(app.style()))
window = MainWindow(); window.timer.stop(); window.age_timer.stop()
window.resize(1280, 800); window.show()

calls = []
original = window.sidebar.tree.itemDelegate().paint


def traced(painter, option, index):
    calls.append(dict(column=index.column(),
                      selected=bool(option.state & QStyle.StateFlag.State_Selected),
                      rect=[option.rect.x(), option.rect.y(),
                            option.rect.width(), option.rect.height()],
                      delegate_selected=window.sidebar.tree.itemDelegate()._is_selected(index)))
    original(painter, option, index)


window.sidebar.tree.itemDelegate().paint = traced
report = {}


def inspect():
    tree = window.sidebar.tree
    item = tree.topLevelItem(0)
    if item is not None:
        tree.setCurrentItem(item)
    app.processEvents()
    tree.viewport().update()
    app.processEvents()
    report['paint_calls'] = calls[:8]
    report['call_count'] = len(calls)
    report['delegate_is_current'] = type(tree.itemDelegate()).__name__
    print(json.dumps(report, indent=2), flush=True)
    window.timer.stop(); window.age_timer.stop(); window.probes.close(); window.work.close()
    window._approved_close = True; window.close(); app.exit(0)


QTimer.singleShot(1500, inspect)
raise SystemExit(app.exec())
