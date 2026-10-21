"""Dark theme QSS: deep slate/obsidian palette."""

QSS = """
* { font-family: "Segoe UI", "Segoe UI Variable", sans-serif; font-size: 13px; }
QMainWindow, QWidget { background: #0b0e14; color: #d5dbe5; }
QSplitter::handle { background: #1a1f2b; }
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical { height: 2px; }
QPushButton {
    background: #1c2331; border: 1px solid #2a3244; border-radius: 6px;
    padding: 6px 12px; color: #d5dbe5;
}
QPushButton:hover { background: #252e42; border-color: #3a4560; }
QPushButton:pressed { background: #1a2130; }
QPushButton:disabled { color: #5a6376; background: #141924; border-color: #1f2534; }
QPushButton#danger { background: #3a1d22; border-color: #5c2b33; color: #f0a3ad; }
QPushButton#danger:hover { background: #4a242b; }
QLineEdit {
    background: #11151f; border: 1px solid #2a3244; border-radius: 6px;
    padding: 6px 10px; color: #d5dbe5; selection-background-color: #31456b;
}
QLineEdit:focus { border-color: #4d6bb3; }
QComboBox {
    background: #11151f; border: 1px solid #2a3244; border-radius: 6px; padding: 5px 10px;
}
QComboBox QAbstractItemView { background: #141924; border: 1px solid #2a3244; }
QTabWidget::pane { border: none; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: #11151f; border: 1px solid #1f2534; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    padding: 7px 14px; margin-right: 2px; color: #8b93a5;
}
QTabBar::tab:selected { background: #1c2331; color: #e8ecf3; border-color: #2a3244; }
QTabBar::tab:hover:!selected { background: #161b28; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #2a3244; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #3a4560; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal { background: #2a3244; border-radius: 5px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QToolTip { background: #1c2331; color: #d5dbe5; border: 1px solid #2a3244; padding: 4px 8px; }
QMenu { background: #141924; border: 1px solid #2a3244; }
QMenu::item:selected { background: #252e42; }
QDialog { background: #0f131c; }
QLabel#muted { color: #8b93a5; }
QLabel#mono { font-family: "Cascadia Code", "Cascadia Mono", Consolas, monospace; }
QFrame#card { background: #11151f; border: 1px solid #1f2534; border-radius: 8px; }
QFrame#card[active="true"] { border-color: #4d6bb3; }
QCheckBox { spacing: 6px; }
QSpinBox {
    background: #11151f; border: 1px solid #2a3244; border-radius: 6px; padding: 4px 8px;
}
"""

# Port badge health colors
COLOR_HTTP_OK = "#3fb950"
COLOR_HTTP_FAIL = "#f0a3ad"
COLOR_UNCHECKED = "#8b93a5"
