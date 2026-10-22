"""Focused pure-view checks complement real first-workspace click tests."""
from types import SimpleNamespace
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QFocusEvent
from ports.sidebar import Sidebar
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.workspace_navigation import WorkspaceNavigation


def test_stopped_row_remains_selected_with_another_live_shell(qt_application):
    profile = WorkspaceProfile(name='Dev', terminals=[TerminalProfile(name='Live'), TerminalProfile(name='Stopped')])
    session = SimpleNamespace(id='live', profile_id=profile.id, definition_id=profile.terminals[0].id,
                              instance_id='one', name='Live', state='ready', listeners=[], age=None)
    nav = WorkspaceNavigation([profile.id], profile.id)
    sidebar = Sidebar()
    sidebar.update_durations = lambda: None
    sidebar.sync([profile], nav, [session], [profile.id], session)
    key = next(key for key, row in sidebar._row_data.items() if row['definition'].id == profile.terminals[1].id)
    target = sidebar._items[key]
    sidebar.tree.setCurrentItem(target)
    sidebar.sync([profile], nav, [session], [profile.id], session)
    assert sidebar.tree.currentItem() is target
    sidebar._sync_actions_to_item(target)
    assert not sidebar.row_actions.buttons['start'].isHidden()
    sidebar.close()


def test_live_row_has_close_rename_and_retry_when_failed(qt_application):
    profile = WorkspaceProfile(name='Dev', terminals=[TerminalProfile(name='Failed')])
    session = SimpleNamespace(id='live', profile_id=profile.id, definition_id=profile.terminals[0].id,
                              instance_id='one', name='Failed', state='failed', listeners=[], age=None)
    sidebar = Sidebar(); sidebar.update_durations = lambda: None
    sidebar.sync([profile], WorkspaceNavigation([profile.id], profile.id), [session], [profile.id], session)
    item = sidebar._items[next(iter(sidebar._row_data))]
    sidebar._sync_actions_to_item(item)
    controls = sidebar.row_actions.buttons
    assert controls['start'].isHidden()
    assert not controls['close'].isHidden()
    assert not controls['retry'].isHidden()
    assert not controls['edit'].isHidden()
    actions = []
    sidebar.terminalAction.connect(lambda name, row: actions.append((name, row['session'])))
    controls['close'].click()
    assert actions == [('close', session)]
    sidebar.close()
