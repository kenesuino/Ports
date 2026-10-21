"""Application entry point with native Windows taskbar identity."""
import ctypes
import os
import sys

from PyQt6.QtWidgets import QApplication
from .icons import app_icon
from .main_window import MainWindow
from .theme import QSS


def main():
    if os.name == "nt":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Ports.Desktop.Workspaces")
    app = QApplication(sys.argv)
    app.setApplicationName("Ports")
    app.setOrganizationName("Ports")
    app.setWindowIcon(app_icon())
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
