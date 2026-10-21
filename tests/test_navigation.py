import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from ports.session_manager import SessionManager
from ports.session_tabs import SessionTabs
from ports.icons import app_icon


def test_tabs_preserve_session_objects_and_order():
    app = QApplication.instance() or QApplication([])
    manager = SessionManager()
    one = manager.create("cmd", name="first")
    two = manager.create("cmd", name="second")
    tabs = SessionTabs()
    tabs.sync(manager.sessions, one)
    original = tuple(manager.sessions)
    tabs.hide(); tabs.show(); tabs.hide()
    tabs.sync(manager.sessions, two)
    assert tuple(manager.sessions) == original
    assert tabs.tabData(tabs.currentIndex()) == two.id
    two.name = "renamed"
    tabs.sync(manager.sessions, two)
    assert tabs.tabText(1) == "renamed"
    assert not app_icon().isNull()


def test_reduced_motion_override():
    from ports.motion import reduced_motion
    assert reduced_motion("on")
    assert not reduced_motion("off")
