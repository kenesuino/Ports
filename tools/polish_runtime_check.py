"""Isolated runtime verification of menu anchor, tree structure and visibility memory."""
import os
import tempfile
from types import SimpleNamespace as S

os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-polish-')
os.environ['APPDATA'] = _temp.name

from PyQt6.QtCore import QTimer, Qt, QPoint
from PyQt6.QtWidgets import QApplication, QMenu, QTabBar
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.main_window import MainWindow
from ports.profiles import WorkspaceProfile, TerminalProfile
from ports.workspace_navigation import WorkspaceNavigation
from ports.session_tabs import SessionTabs
from ports.theme import QSS
import json

app = QApplication(['ports-polish-check']); app.setStyleSheet(QSS)
window = MainWindow(); window.timer.stop(); window.age_timer.stop()
window.resize(1280, 800); window.show()
profile = WorkspaceProfile(name='UI check', terminals=[TerminalProfile(name='Terminal')])
window.config.profiles = [profile]
window.sidebar.set_profiles([profile]); window.load_workspace(profile.id)
mock = S(id='one', profile_id=profile.id, instance_id='one', definition_id=profile.terminals[0].id,
         name='Terminal', shell='cmd', state='ready', listeners=[], current_cwd='', cwd='', last_error='')
window.sidebar.update_durations = lambda: None
window.sidebar.sync([profile], window.navigation, [mock], [profile.id], mock)
window.tabs.sync([mock], mock)
report = {}


def inspect_menu():
    popup = QApplication.activePopupWidget()
    if not isinstance(popup, QMenu):
        report['menu_error'] = 'No menu visible'
        return
    expected = window.sidebar.manage_button.mapToGlobal(window.sidebar.manage_button.rect().bottomLeft())
    actual = popup.geometry().topLeft()
    report['menu_actual'] = [actual.x(), actual.y()]
    report['button_anchor'] = [expected.x(), expected.y()]
    report['menu_aligned'] = abs(actual.x() - expected.x()) <= 3 and abs(actual.y() - expected.y()) <= 3
    popup.close()


def dispose(target):
    target.timer.stop(); target.age_timer.stop(); target.probes.close(); target.work.close()
    target._approved_close = True; target.close()


def run():
    QTimer.singleShot(100, inspect_menu)
    window.profile_action('manage', '')
    report['one_instance_header_hidden'] = not any(k[0] == 'instance' for k in window.sidebar._items)
    report['bottom_buttons_removed'] = not hasattr(window.sidebar, 'start_button')
    report['rename_hover_removed'] = 'rename' not in window.sidebar.row_actions.buttons
    close = window.tabs.tabs.tabButton(0, QTabBar.ButtonPosition.RightSide)
    report['custom_close'] = close.objectName() == 'tabCloseButton'
    window._panel_visibility_changed(False)
    assert not window.config.ports_inspector_visible
    dispose(window)
    closed = MainWindow(); closed.timer.stop(); closed.resize(1280, 800); closed.show(); app.processEvents()
    report['reopen_closed_remembered'] = not closed.config.ports_inspector_visible and closed.inspector.isHidden()
    closed._panel_visibility_changed(True)
    dispose(closed)
    opened = MainWindow(); opened.timer.stop(); opened.resize(1280, 800); opened.show(); app.processEvents()
    report['reopen_open_remembered'] = opened.config.ports_inspector_visible and not opened.inspector.isHidden()
    dispose(opened)
    report['passed'] = all(report.get(key) for key in ('menu_aligned', 'one_instance_header_hidden', 'bottom_buttons_removed',
        'rename_hover_removed', 'custom_close', 'reopen_closed_remembered', 'reopen_open_remembered'))
    print(json.dumps(report, indent=2), flush=True)
    app.exit(0 if report['passed'] else 1)

QTimer.singleShot(0, run)
raise SystemExit(app.exec())
