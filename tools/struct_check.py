"""Assert navigation-only loading, expanded left rail and right inspector."""
import os
import tempfile
os.environ.pop('QT_QPA_PLATFORM', None)
_temp = tempfile.TemporaryDirectory(prefix='ports-struct-')
os.environ['APPDATA'] = _temp.name
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.main_window import MainWindow
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.theme import QSS
import json

app = QApplication(['ports-struct']); app.setStyleSheet(QSS)
window = MainWindow(); window.timer.stop(); window.resize(1280, 800); window.show()
profile = WorkspaceProfile(name='Dev', terminals=[TerminalProfile(name='Frontend'), TerminalProfile(name='API')])
window.config.profiles = [profile]; window.sidebar.set_profiles([profile]); window.load_workspace(profile.id)


def check():
    report = dict(left_width=window.sidebar.width(), left_collapse_removed=not hasattr(window.sidebar, 'collapse_button'),
                  saved_terminal_rows=len(window.sidebar._row_data), sessions_started=len(window.manager.sessions),
                  right_ports_inspector=window.splitter.widget(2) is window.inspector,
                  no_bulk_run=not hasattr(window.sidebar, 'run_button'),
                  tabs=window.tabs.tabs.count(), header_height=window.header.height())
    assert report['left_width'] >= 220 and report['left_collapse_removed']
    assert report['saved_terminal_rows'] == 2 and report['sessions_started'] == 0
    assert report['right_ports_inspector'] and report['no_bulk_run'] and report['tabs'] == 0
    report['passed'] = True
    print(json.dumps(report, indent=2), flush=True)
    window.age_timer.stop(); window.probes.close(); window.work.close(); window._approved_close = True; window.close(); app.exit(0)

QTimer.singleShot(1000, check)
raise SystemExit(app.exec())
