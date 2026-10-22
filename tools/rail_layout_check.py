"""Runtime check: dropdown loads on selection, manage sits below the tree."""
import os
import tempfile

os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-rail-')
os.environ['APPDATA'] = _temp.name

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.main_window import MainWindow
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.theme import QSS
import json

app = QApplication(['ports-rail-check']); app.setStyleSheet(QSS)
window = MainWindow(); window.timer.stop(); window.age_timer.stop()
window.resize(1280, 800); window.show()
profile = WorkspaceProfile(name='Frontend', terminals=[TerminalProfile(name='Dev server')])
other = WorkspaceProfile(name='Backend', terminals=[TerminalProfile(name='API')])
window.config.profiles = [profile, other]
window.sidebar.set_profiles([profile, other])
report = {}


def inspect():
    report['combo_items'] = [window.sidebar.profile_combo.itemText(i) for i in range(window.sidebar.profile_combo.count())]
    report['loaded_after_combo'] = list(window.navigation.loaded)
    report['selected_after_combo'] = window.navigation.selected
    report['tree_rows'] = len(window.sidebar._row_data)
    manage_geometry = window.sidebar.manage_button.mapTo(window.sidebar, QPoint(0, 0))
    tree_geometry = window.sidebar.tree.mapTo(window.sidebar, QPoint(0, 0))
    report['manage_below_tree'] = manage_geometry.y() > tree_geometry.y()
    report['combo_above_tree'] = window.sidebar.profile_combo.mapTo(window.sidebar, QPoint(0, 0)).y() < tree_geometry.y()
    report['no_load_button'] = not any(b.text() == 'Load workspace' for b in window.sidebar.findChildren(type(window.sidebar.manage_button)))
    report['new_terminal_present'] = window.sidebar.new_terminal_button.text() == 'New terminal'
    report['passed'] = all(report[key] for key in ('loaded_after_combo', 'tree_rows', 'manage_below_tree',
                                                  'combo_above_tree', 'no_load_button', 'new_terminal_present'))
    print(json.dumps(report, indent=2), flush=True)
    window.timer.stop(); window.age_timer.stop(); window.probes.close(); window.work.close()
    window._approved_close = True; window.close(); app.exit(0 if report['passed'] else 1)


def choose():
    index = window.sidebar.profile_combo.findText('Frontend')
    window.sidebar.profile_combo.setCurrentIndex(index)


from PyQt6.QtCore import QPoint
QTimer.singleShot(300, choose)
QTimer.singleShot(900, inspect)
QTimer.singleShot(12000, lambda: app.exit(3))
raise SystemExit(app.exec())
