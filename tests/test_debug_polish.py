"""Focused post-evidence checks for single-instance layout and tab-close targeting."""
from types import SimpleNamespace as S
from ports.profiles import WorkspaceProfile, TerminalProfile
from ports.sidebar import Sidebar
from ports.session_tabs import SessionTabs
from ports.workspace_navigation import WorkspaceNavigation
from PyQt6.QtWidgets import QTabBar


def session(profile, instance):
    return S(id=instance, profile_id=profile.id, instance_id=instance,
             definition_id=profile.terminals[0].id, name='Terminal', shell='cmd',
             state='ready', listeners=[], current_cwd='', cwd='', last_error='')


def test_heading_reparent_single_multiple_single(qt_application):
    profile = WorkspaceProfile(name='test', terminals=[TerminalProfile()])
    first, second = session(profile, 'one'), session(profile, 'two')
    sidebar = Sidebar(); sidebar.update_durations = lambda: None
    nav = WorkspaceNavigation([profile.id], profile.id)
    sidebar.sync([profile], nav, [first], [profile.id], first)
    key = next(iter(sidebar._row_data))
    original = sidebar._items[key]
    assert original.parent() is sidebar._items[('workspace', profile.id)]
    assert not any(k[0] == 'instance' for k in sidebar._items)
    sidebar.sync([profile], nav, [first, second], [profile.id], first)
    assert sum(k[0] == 'instance' for k in sidebar._items) == 2
    assert sidebar._items[key] is original
    sidebar.sync([profile], nav, [first], [profile.id], first)
    assert sidebar._items[key] is original
    assert original.parent() is sidebar._items[('workspace', profile.id)]
    assert not any(k[0] == 'instance' for k in sidebar._items)
    assert not any(hasattr(sidebar, name) for name in ('start_button', 'edit_button', 'close_button', 'retry_button', 'remove_button'))
    assert 'rename' not in sidebar.row_actions.buttons
    sidebar.close()


def test_close_button_targets_stable_session_after_reorder(qt_application):
    profile = WorkspaceProfile(terminals=[TerminalProfile()])
    first, second = session(profile, 'one'), session(profile, 'two')
    tabs = SessionTabs(); tabs.sync([first, second], first)
    close = tabs.tabButton(0, QTabBar.ButtonPosition.RightSide)
    assert close.objectName() == 'tabCloseButton'
    assert close.width() == 24 and close.toolTip()
    events = []
    tabs.closeRequested.connect(events.append)
    tabs.sync([second, first], second)
    close.click()
    assert events == [first.id]
    tabs.close()
