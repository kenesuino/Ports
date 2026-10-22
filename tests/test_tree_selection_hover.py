"""Real tree clicks must select definitions even when they have no live shell."""
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ports.main_window import MainWindow
from ports.profiles import TerminalProfile, WorkspaceProfile


def test_first_workspace_definition_selection_survives_refresh(tmp_path, monkeypatch, qt_application):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    window = MainWindow()
    window.timer.stop()
    first = WorkspaceProfile(name='First workspace', terminals=[TerminalProfile(name='API'), TerminalProfile(name='Worker')])
    second = WorkspaceProfile(name='Second workspace', terminals=[TerminalProfile(name='Other')])
    window.config.profiles = [first, second]
    window.sidebar.set_profiles([first, second])
    window.load_workspace(first.id)
    window.load_workspace(second.id)
    window.resize(1280, 800)
    window.show()
    qt_application.processEvents()
    try:
        tree = window.sidebar.tree
        target_key = next(key for key, row in window.sidebar._row_data.items()
                          if row['scope'] == first.id and row['definition'].id == first.terminals[0].id)
        target = window.sidebar._items[target_key]
        tree.scrollToItem(target)
        qt_application.processEvents()
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton,
                         pos=tree.visualItemRect(target).center())
        qt_application.processEvents()
        assert window.navigation.selected == first.id
        assert tree.currentItem() is target
        window._sync_workspace_panel()
        assert tree.currentItem() is target
        window.sidebar._sync_actions_to_item(target)
        assert not window.sidebar.row_actions.buttons['start'].isHidden()
        assert window.manager.sessions == []
    finally:
        window.age_timer.stop()
        window.probes.close()
        window.work.close()
        window._approved_close = True
        window.close()


def test_hover_actions_target_row_not_previous_selection(tmp_path, monkeypatch, qt_application):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    window = MainWindow()
    window.timer.stop()
    profile = WorkspaceProfile(name='Workspace', terminals=[TerminalProfile(name='API'), TerminalProfile(name='Worker')])
    window.config.profiles = [profile]
    window.load_workspace(profile.id)
    window.resize(1280, 800)
    window.show()
    qt_application.processEvents()
    try:
        sidebar = window.sidebar
        tree = sidebar.tree
        keys = [key for key, row in sidebar._row_data.items() if row['scope'] == profile.id]
        tree.setCurrentItem(sidebar._items[keys[0]])
        hovered = sidebar._items[keys[1]]
        QTest.mouseMove(tree.viewport(), tree.visualItemRect(hovered).center())
        QTest.qWait(80)
        qt_application.processEvents()
        from PyQt6.QtCore import QEvent, QPointF
        from PyQt6.QtGui import QMouseEvent
        # Deliver a real viewport mouse-move event independently of whether
        # this Windows test host has granted the window native foreground focus.
        position = tree.visualItemRect(hovered).center()
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(position),
                            QPointF(tree.viewport().mapToGlobal(position)),
                            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(), event)
        toolbar = sidebar.row_actions
        assert not toolbar.isHidden()
        assert tree.viewport().isAncestorOf(toolbar)
        before = {id(w) for w in QApplication.topLevelWidgets() if w.isVisible()}
        with patch.object(window, '_panel_start') as start:
            toolbar.buttons['start'].click()
            start.assert_called_once()
            assert start.call_args.args[0]['definition'].id == profile.terminals[1].id
        assert {id(w) for w in QApplication.topLevelWidgets() if w.isVisible()} <= before
        sidebar._sync_actions_to_item(hovered)
        old_geometry = tree.visualItemRect(hovered)
        window._sync_workspace_panel()
        assert sidebar._items[keys[1]] is hovered
        assert tree.visualItemRect(hovered) == old_geometry
    finally:
        window.age_timer.stop()
        window.probes.close()
        window.work.close()
        window._approved_close = True
        window.close()
