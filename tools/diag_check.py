"""Measure the empty-state caption height and the tree selection geometry."""
import os
import tempfile

os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-diag-')
os.environ['APPDATA'] = _temp.name

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QLabel
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.__main__ import _dark_palette
from ports.main_window import MainWindow
from ports.style import PortsStyle
from ports.theme import QSS
import json

app = QApplication(['ports-diag'])
app.setStyle('Fusion'); app.setPalette(_dark_palette()); app.setStyleSheet(QSS)
app.setStyle(PortsStyle(app.style()))
window = MainWindow(); window.timer.stop(); window.age_timer.stop()
window.resize(1280, 800); window.show()
report = {}


def inspect():
    stack = window.stack
    empty = stack.widget(0)
    labels = empty.findChildren(QLabel)
    caption = next((l for l in labels if 'Save a workspace' in (l.text() or '')), None)
    if caption is None:
        report['caption_error'] = 'caption label not found'
    else:
        report['caption_text'] = caption.text()[:40]
        report['caption_height'] = caption.height()
        report['caption_needed_height'] = caption.heightForWidth(caption.width())
        report['caption_width'] = caption.width()
        report['caption_clipped'] = caption.height() < caption.heightForWidth(caption.width())
    buttons = empty.findChildren(type(window.header.restart_btn))
    for button in buttons:
        if 'Create workspace' in (button.text() or ''):
            report['button_geometry'] = [button.x(), button.y(), button.width(), button.height()]
            report['caption_geometry'] = [caption.x(), caption.y(), caption.width(), caption.height()] if caption else None
    tree = window.sidebar.tree
    report['delegate'] = type(tree.itemDelegate()).__name__
    report['viewport_size'] = [tree.viewport().width(), tree.viewport().height()]
    report['column_widths'] = [tree.columnWidth(0), tree.columnWidth(1)]
    report['column_1_visible_width'] = tree.columnWidth(1)
    print(json.dumps(report, indent=2), flush=True)
    window.timer.stop(); window.age_timer.stop(); window.probes.close(); window.work.close()
    window._approved_close = True; window.close(); app.exit(0)


QTimer.singleShot(1200, inspect)
raise SystemExit(app.exec())
