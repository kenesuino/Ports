"""Application entry point: dark native chrome, palette, and main window."""

from __future__ import annotations

import ctypes
import os
import sys

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from . import native
from .icons import app_icon
from .main_window import MainWindow
from .style import PortsStyle
from .theme import CANVAS, PANEL, QSS, TEXT, TEXT_MUTED

APP_USER_MODEL_ID = "Ports.Desktop"


def _dark_palette() -> QPalette:
    """Set before show() so no light frame flashes on launch."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(CANVAS))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(PANEL))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(CANVAS))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(PANEL))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3a4048"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.Text, QColor("#5c636d"))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.ButtonText, QColor("#5c636d"))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.WindowText, QColor("#5c636d"))
    return palette


def main() -> int:
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                APP_USER_MODEL_ID)
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Ports")
    app.setOrganizationName("Ports")
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setStyleSheet(QSS)
    app.setStyle(PortsStyle(app.style()))

    window = MainWindow()
    window.show()
    native.apply_window_chrome(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
