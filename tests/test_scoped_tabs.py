"""Scoped tabs keep the original session/view objects alive."""
from types import SimpleNamespace
from unittest.mock import patch
from ports.main_window import MainWindow
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.port_monitor import Listener
from ports.workspace_navigation import OTHER


def test_workspace_switch_unpin_reload_and_inspector_scope(tmp_path, monkeypatch, qt_application):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    window = MainWindow(); window.timer.stop()
    a = WorkspaceProfile(name='A', terminals=[TerminalProfile(name='API')])
    b = WorkspaceProfile(name='B', terminals=[TerminalProfile(name='Worker')])
    window.config.profiles = [a, b]; window.sidebar.set_profiles([a, b])
    window.load_workspace(a.id); window.load_workspace(b.id)
    first = SimpleNamespace(id='a1', name='API', profile_id=a.id, instance_id='one', definition_id=a.terminals[0].id,
        listeners=[Listener('127.0.0.1', 3000, None)], state='ready', current_cwd='', cwd='', shell='cmd', last_error='', expected_ports=[],
        can_restart=lambda: False, restart_reason=lambda: 'no command', view=object(), age=None)
    second = SimpleNamespace(**dict(first.__dict__, id='b1', name='Worker', profile_id=b.id, definition_id=b.terminals[0].id,
                                   listeners=[Listener('::1', 4000, None)], view=object()))
    first.label_scope = 'a'; second.label_scope = 'b'
    window.manager.sessions = [first, second]
    # No pane is installed: session identity/selection can be checked without
    # creating a second terminal emulator or invoking any shell command.
    with patch.object(window.sidebar, 'update_durations'):
        window.select_scope(a.id)
        assert window.manager.active is first
        assert window.tabs.tabs.count() == 1 and window.tabs.tabs.tabData(0) == first.id
        original_view = first.view
        window.select_scope(b.id)
        assert window.manager.active is second and first.view is original_view
        window.select_scope(a.id)
        assert window.manager.active is first
        external = Listener('0.0.0.0', 9000, None)
        window.inspector.update_external([external])
        window._refresh_merged_ports()
        assert {key[1] for key in window.inspector.ports_list._rows if key[0] == 'session'} == {'a1'}
        window._ports_scope_changed('all')
        assert {key[1] for key in window.inspector.ports_list._rows if key[0] == 'session'} == {'a1', 'b1'}
        window.unpin_workspace(a.id)
        assert window.navigation.selected == OTHER and window.manager.active is first
        assert a in window.config.profiles and len(window.manager.sessions) == 2
        window.load_workspace(a.id)
        assert window.manager.active is first and len(window.manager.sessions) == 2
    with patch.object(window.sidebar, 'update_durations'):
        window.select_scope(a.id)
        window._remove_session(first)
        assert window.navigation.selected == a.id and window.manager.active is None
        assert window.manager.sessions == [second]
        assert window.tabs.tabs.count() == 0
    window.manager.sessions = []
    window.timer.stop(); window.age_timer.stop(); window.probes.close(); window.work.close()
    window._approved_close = True; window.close()
