"""Interaction regressions: native child controls and workspace instance targeting."""
from types import SimpleNamespace

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ports.port_monitor import Listener, OwnerIdentity
from ports.profiles import TerminalProfile, WorkspaceProfile
from ports.session_manager import SessionManager
from ports.sidebar import PortRow
from ports.workspace_navigation import derive_rows, WorkspaceNavigation


def live(profile, definition, instance, state="ready"):
    return SimpleNamespace(id=instance + definition.id, profile_id=profile.id,
                           definition_id=definition.id, instance_id=instance,
                           name=definition.name, shell=definition.shell,
                           state=state, listeners=[], last_error="")


def test_port_hover_actions_are_children_not_windows(qt_application):
    row = PortRow(Listener("127.0.0.1", 3000, OwnerIdentity("windows", 7, 1, "n" * 100)))
    row.resize(230, 30)
    row.show()
    qt_application.processEvents()
    windows = set(QApplication.topLevelWidgets())
    port_rect = row.port.geometry()
    QTest.mouseMove(row, row.rect().center())
    row.setFocus()
    qt_application.processEvents()
    for action in (row.open_button, row.kill_button):
        assert row.isAncestorOf(action)
        assert not action.isWindow()
        assert row.rect().contains(action.mapTo(row, action.rect().center()))
    assert set(QApplication.topLevelWidgets()) == windows
    assert row.port.geometry() == port_rect
    assert row.width() == 230
    row.close()


def test_panel_keeps_both_copies_and_missing_definitions():
    a, b = TerminalProfile(name="A"), TerminalProfile(name="B")
    profile = WorkspaceProfile(name="Dev", terminals=[a, b])
    one, two = live(profile, a, "copy1"), live(profile, a, "copy2")
    rows = derive_rows(profile, [one, two])
    assert len(rows) == 4
    assert {r['session'].id for r in rows if r['session']} == {one.id, two.id}
    assert {r['instance_id'] for r in rows} == {'copy1', 'copy2'}
    assert len({r['key'] for r in rows}) == 4


def test_panel_preserves_row_identity_and_edit_does_not_run(qt_application):
    definition = TerminalProfile(name="A")
    profile = WorkspaceProfile(name="Dev", terminals=[definition])
    session = live(profile, definition, "copy")
    from ports.sidebar import Sidebar
    panel = Sidebar()
    nav = WorkspaceNavigation([profile.id], profile.id)
    panel.sync([profile], nav, [session], [profile.id], session)
    key = next(iter(panel._row_data))
    row = panel._items[key]
    panel.sync([profile], nav, [session], [profile.id], session)
    assert panel._items[key] is row
    assert not hasattr(panel, 'run_button')
    assert panel.row_actions.buttons['edit'].accessibleName() == 'Edit saved terminal definition'
    panel.close()


def test_start_definition_only_once_in_target_instance():
    a, b = TerminalProfile(name="A"), TerminalProfile(name="B")
    profile = WorkspaceProfile(name="Dev", terminals=[a, b])
    manager = SessionManager()
    first = manager.launch_definition(profile, b.id, "copy2")
    again = manager.launch_definition(profile, b.id, "copy2")
    assert first is again
    assert len(manager.sessions) == 1
    assert first.definition_id == b.id and first.instance_id == "copy2"
    other = manager.launch_definition(profile, b.id, "copy1")
    same = manager.launch_definition(profile, a.id, '')
    again_same = manager.launch_definition(profile, a.id, '')
    assert same is again_same
    assert len(manager.sessions) == 3
    assert other is not first
    assert len({s.id for s in manager.sessions}) == 3
