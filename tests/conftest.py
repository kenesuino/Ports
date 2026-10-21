import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)


@pytest.fixture(scope='session', autouse=True)
def qt_application():
    # Real WebEngine requires argv[0]; an empty list aborts native Chromium.
    app = QApplication.instance() or QApplication(['ports-tests'])
    yield app
