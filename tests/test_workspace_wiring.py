"""Window wiring without starting shells; every fixture uses isolated config."""
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from ports.main_window import MainWindow
from ports.profiles import WorkspaceProfile, TerminalProfile
from ports.session_manager import SessionManager


@pytest.fixture
def window(tmp_path, monkeypatch, qt_application):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    result = MainWindow()
    result.timer.stop()
    result.resize(1280, 800)
    result.show()
    qt_application.processEvents()
    yield result
    result.timer.stop()
    result.probes.close()
    result.work.close()
    result._approved_close = True
    result.close()
    result.deleteLater()
    qt_application.processEvents()


def profiles(window):
    a = WorkspaceProfile(name='A', terminals=[TerminalProfile(name='First'), TerminalProfile(name='Second')])
    b = WorkspaceProfile(name='B', terminals=[TerminalProfile(name='Other')])
    window.config.profiles = [a, b]
    window.sidebar.set_profiles([a, b])
    return a, b


def test_selection_updates_panel_without_launching_or_hiding_tabs(window):
    a, b = profiles(window)
    window.load_workspace(a.id)
    assert [r['definition'].name for r in window.sidebar._row_data.values() if r['scope'] == a.id] == ['First', 'Second']
    window.load_workspace(b.id)
    assert [r['definition'].name for r in window.sidebar._row_data.values() if r['scope'] == b.id] == ['Other']
    assert window.manager.sessions == []
    assert not window.tabs.isHidden()


def test_start_review_cancel_then_launch_only_clicked_definition(window):
    a, _ = profiles(window)
    window.load_workspace(a.id)
    row = next(r for r in window.sidebar._row_data.values() if r['definition'].id == a.terminals[1].id)
    with patch.object(window, '_review_profile', return_value=False), patch.object(window.manager, 'launch_definition') as launch:
        window._panel_start(row)
        launch.assert_not_called()
    with patch.object(window, '_review_profile', return_value=True), patch.object(window.manager, 'launch_definition') as launch:
        window._panel_start(row)
        launch.assert_called_once()
        assert launch.call_args.args[:2] == (a, a.terminals[1].id)
        assert launch.call_args.args[2]


def test_edit_focuses_definition_without_launch(window):
    a, _ = profiles(window)
    window.load_workspace(a.id)
    row = next(r for r in window.sidebar._row_data.values() if r['definition'].id == a.terminals[1].id)
    with patch.object(window, 'profile_action') as action:
        window._panel_edit(row)
        action.assert_called_once_with('edit', a.id, terminal_id=a.terminals[1].id)


def test_panel_resizes_without_overwriting_user_preference(window, qt_application):
    window.config.ports_inspector_visible = True
    window.config.ports_inspector_width = 250
    window._apply_panel_visibility()
    window.resize(900, 700)
    qt_application.processEvents()
    assert window.inspector.isHidden(), (window.width(), window.minimumSizeHint().width(), window.minimumWidth())
    assert window.config.ports_inspector_visible
    assert window.config.ports_inspector_width == 250
    window.resize(1280, 800)
    qt_application.processEvents()
    assert not window.inspector.isHidden()
    window.toggle_workspace_panel()
    assert window.inspector.isHidden()
    window.resize(900, 700)
    window.resize(1280, 800)
    qt_application.processEvents()
    assert window.inspector.isHidden()
    assert not window.config.ports_inspector_visible


def test_close_retry_and_focus_target_clicked_session(window):
    from types import SimpleNamespace
    selected = SimpleNamespace(id='clicked')
    row = {'session': selected}
    with patch.object(window.manager, 'set_active') as focus, patch.object(window, 'close_session') as close, patch.object(window, 'retry') as retry:
        window._panel_activated(row)
        window._panel_close(row)
        window._panel_retry(row)
        focus.assert_called_once_with(selected)
        close.assert_called_once_with(selected)
        retry.assert_called_once_with('clicked')


def test_header_symbols_distinct_and_actions_tooltipped(window):
    header = window.header
    controls = [header.restart_btn, header.ctrlc_btn, header.kill_btn, header.clear_btn]
    assert all(not c.text() and c.accessibleName() and c.toolTip() for c in controls)
    assert len({c.icon().cacheKey() for c in controls}) == 4
    assert 'Ctrl+C' in header.ctrlc_btn.toolTip()
    assert 'process running' in header.clear_btn.toolTip()
