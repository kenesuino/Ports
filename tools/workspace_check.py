"""Real Windows/WSL per-terminal navigation, elapsed age and restart memory check."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--width', type=int, default=1280)
parser.add_argument('--scale', default='1')
parser.add_argument('--wsl', action='store_true')
args = parser.parse_args()
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ['QT_SCALE_FACTOR'] = args.scale
_temporary = tempfile.TemporaryDirectory(prefix='ports-nav-')
os.environ['APPDATA'] = _temporary.name
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from ports.main_window import MainWindow
from ports.profiles import WorkspaceProfile, TerminalProfile
from ports.__main__ import _dark_palette
from ports.theme import QSS
from ports.workspace_navigation import OTHER
from ports import config_store

app = QApplication(['ports-navigation-check'])
app.setPalette(_dark_palette()); app.setStyle('Fusion'); app.setStyleSheet(QSS)
window = MainWindow(); window.resize(args.width, 800); window.show()
a = WorkspaceProfile(name='Frontend', terminals=[TerminalProfile(name='Server', shell='cmd', startup_cmd='echo PORTS_SCOPED_OK')])
b = WorkspaceProfile(name='Backend', terminals=[TerminalProfile(name='API', shell='powershell', startup_cmd='Write-Output PORTS_BACKEND_OK')])
if args.wsl:
    b.terminals[0].shell = 'wsl'; b.terminals[0].distro = 'Ubuntu'; b.terminals[0].startup_cmd = 'echo PORTS_BACKEND_OK'
a.approve(); b.approve()
window.config.profiles = [a, b]; window.sidebar.set_profiles([a, b])
report = {}
window.load_workspace(a.id); window.load_workspace(b.id)
assert not window.manager.sessions
window.select_scope(a.id)
window._panel_start(dict(scope=a.id, definition=a.terminals[0], instance_id=''))
first = window.manager.sessions[0]
window.select_scope(b.id)
window._panel_start(dict(scope=b.id, definition=b.terminals[0], instance_id=''))
second = window.manager.sessions[1]


def check():
    try:
        assert first.pty and first.pty.isalive(), first.last_error
        assert second.pty and second.pty.isalive(), second.last_error
        original = first.view
        original_pid = first.pty.pid
        window.select_scope(a.id)
        assert window.tabs.tabs.count() == 1 and window.manager.active is first
        window.select_scope(b.id)
        assert window.tabs.tabs.count() == 1 and window.manager.active is second
        window.select_scope(a.id)
        assert first.view is original and first.pty.pid == original_pid
        window.unpin_workspace(a.id)
        assert window.navigation.selected == OTHER and window.manager.active is first
        window.load_workspace(a.id)
        assert len(window.manager.sessions) == 2 and window.manager.active is first
        assert first.age.seconds() is not None and first.age.seconds() >= 1
        assert window.sidebar.width() >= 220
        assert not hasattr(window.sidebar, 'collapse_button')
        assert not hasattr(window.sidebar, 'ports_list')
        report.update(identities_preserved=True, age=first.age.seconds(), left_width=window.sidebar.width(),
                      visible_tabs=window.tabs.tabs.count(), states=[s.state for s in window.manager.sessions])
        if args.wsl and second.state != 'ready':
            report['backend_error'] = second.last_error
        first.view.page().runJavaScript('window.portsBufferText()', got_buffer)
    except Exception as exc:
        report['error'] = str(exc)
        finish(False)


def got_buffer(text):
    report['buffer_preserved'] = 'PORTS_SCOPED_OK' in text
    root = Path(__file__).resolve().parents[1] / 'artifacts'; root.mkdir(exist_ok=True)
    window.grab().save(str(root / f'workspace-nav-{args.width}-{args.scale}.png'))
    if args.wsl:
        second.view.page().runJavaScript('window.portsBufferText()', lambda value: got_backend(value))
    else:
        finish(report['buffer_preserved'])


def got_backend(text):
    report['backend_output'] = text
    report['backend_command_rendered'] = 'PORTS_BACKEND_OK' in text
    finish(report['buffer_preserved'] and report['backend_command_rendered'] and second.state == 'ready')


def finish(ok):
    window._save_navigation()
    window.timer.stop(); window.age_timer.stop(); window.probes.close()
    for session in window.manager.sessions:
        session.prepare_close(); session.close()
    frozen = first.age.seconds()
    assert first.age.seconds() == frozen
    window.work.close(); window._approved_close = True; window.close()
    # Opening a second window with same saved config restores names only.
    restored = MainWindow(); restored.timer.stop(); restored.age_timer.stop()
    report['restored_loaded_names'] = len(restored.navigation.loaded)
    report['restored_session_count'] = len(restored.manager.sessions)
    report['passed'] = bool(ok and len(restored.navigation.loaded) == 2 and not restored.manager.sessions)
    restored.probes.close(); restored.work.close(); restored._approved_close = True; restored.close()
    print(json.dumps(report, indent=2), flush=True)
    app.exit(0 if report['passed'] else 1)

QTimer.singleShot(14000 if not args.wsl else 22000, check)
QTimer.singleShot(40000, lambda: app.exit(3))
raise SystemExit(app.exec())
