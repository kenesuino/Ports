"""Hover regression now exercises the right inspector's single port renderer."""
import os
import tempfile
os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-hover-')
os.environ['APPDATA'] = _temp.name
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.main_window import MainWindow
from ports.port_monitor import Listener, OwnerIdentity
from ports.theme import QSS
import json

app = QApplication(['ports-hover-check']); app.setStyleSheet(QSS)
window = MainWindow(); window.timer.stop(); window.resize(1280, 800); window.show()
listener = Listener('127.0.0.1', 4173, OwnerIdentity('windows', 4242, 1, 'node.exe'))
window.inspector.external_open = True
window.inspector.update_external([listener]); window._refresh_merged_ports()
report = {}


def check():
    row = next(iter(window.inspector.ports_list._rows.values()))
    before = {id(w) for w in QApplication.topLevelWidgets() if w.isVisible()}
    port_position = row.port.geometry()
    QTest.mouseMove(row, row.rect().center()); row.setFocus(); app.processEvents()
    report['no_extra_hover_windows'] = {id(w) for w in QApplication.topLevelWidgets() if w.isVisible()} <= before
    report['actions_contained'] = all(row.isAncestorOf(button) and not button.isWindow() and row.rect().contains(button.mapTo(row, button.rect().center())) for button in (row.open_button, row.kill_button))
    report['port_geometry_stable'] = port_position == row.port.geometry()
    report['passed'] = all(report.values())
    print(json.dumps(report, indent=2), flush=True)
    window.timer.stop(); window.age_timer.stop(); window.probes.close(); window.work.close()
    window._approved_close = True; window.close(); app.exit(0 if report['passed'] else 1)

QTimer.singleShot(1500, check)
raise SystemExit(app.exec())
