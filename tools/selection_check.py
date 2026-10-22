"""Confirm the selected tree row is one continuous band, not two boxes."""
import os
import tempfile

os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-sel-')
os.environ['APPDATA'] = _temp.name

from PyQt6.QtCore import QPoint, QTimer, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.__main__ import _dark_palette
from ports.main_window import MainWindow
from ports.style import PortsStyle
from ports.theme import QSS
import json

app = QApplication(['ports-sel'])
app.setStyle('Fusion'); app.setPalette(_dark_palette()); app.setStyleSheet(QSS)
app.setStyle(PortsStyle(app.style()))
window = MainWindow(); window.timer.stop(); window.age_timer.stop()
window.resize(1280, 800); window.show()
report = {}


def inspect():
    tree = window.sidebar.tree
    tree.resize(240, 400); tree.show(); app.processEvents()
    item = tree.topLevelItem(0)
    if item is None:
        report['error'] = 'no top-level row'
    else:
        tree.setCurrentItem(item)
        app.processEvents()
        rect = tree.visualItemRect(item)
        image = tree.viewport().grab().toImage()
        # Sample near the top of the row, above the text baseline, so the
        # scan measures the selection band rather than glyph pixels.
        scan = rect.top() + 3
        row_pixels = []
        for x in range(rect.left(), rect.right()):
            color = image.pixelColor(x, scan)
            row_pixels.append((x, color.red(), color.green(), color.blue()))
        report['row_left_x'] = rect.left()
        report['row_right_x'] = rect.right()
        report['first_pixels'] = row_pixels[:6]
        report['last_pixels'] = row_pixels[-6:]
        report['max_channel'] = max(max(p[1], p[2], p[3]) for p in row_pixels)
        report['lit_pixels'] = sum(1 for p in row_pixels if max(p[1], p[2], p[3]) > 24)
        # A continuous band means every pixel in the row is the same lit value.
        values = {(p[1], p[2], p[3]) for p in row_pixels}
        report['distinct_colors'] = len(values)
        report['continuous'] = (report['lit_pixels'] == len(row_pixels)
                                and len(values) == 1)
    window.grab().save('artifacts/selection-band.png')
    report['passed'] = bool(report.get('continuous'))
    print(json.dumps(report, indent=2), flush=True)
    window.timer.stop(); window.age_timer.stop(); window.probes.close(); window.work.close()
    window._approved_close = True; window.close(); app.exit(0 if report['passed'] else 1)


QTimer.singleShot(1200, inspect)
raise SystemExit(app.exec())
