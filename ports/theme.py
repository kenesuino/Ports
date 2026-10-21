"""Obsidian desktop palette; session accents are applied to header/selection."""
QSS = '''
* { font-family: "Segoe UI"; font-size: 12px; }
QMainWindow, QWidget { background:#0b111c; color:#dce5f2; }
QWidget:disabled { color:#75849a; }
QLabel { background:transparent; }
QLabel#muted { color:#a0afc4; }
QLabel#brand { font-size:19px; font-weight:700; color:#e5ecf6; padding:4px 0 10px; }
QLabel#sectionLabel { color:#a0afc4; font-size:10px; font-weight:600; }
QLabel#workspaceTitle { font-size:15px; font-weight:600; }
QLabel#emptyTitle { font-size:23px; font-weight:600; padding:12px; }
QPushButton { background:#1a2434; border:1px solid #2c3a50; border-radius:5px; padding:7px 10px; }
QPushButton:hover { background:#29354a; border-color:#4a607d; }
QPushButton:pressed { background:#35435a; }
QPushButton:focus { border:1px solid #8ab4ff; }
QPushButton:disabled { background:#131d2b; color:#77869c; border-color:#233148; }
QPushButton#danger { color:#f6a4b4; border-color:#6a3e50; background:#302030; }
QPushButton#danger:hover { background:#45283a; }
QPushButton#portBadge { background:#152e2c; border:1px solid #29574d; color:#9ce0c4; font-family:Consolas; padding:3px 7px; border-radius:5px; }
QPushButton#portBadge:hover { background:#20443b; border-color:#73c9aa; }
QLineEdit, QPlainTextEdit, QListWidget { background:#101a28; border:1px solid #2c3a50; border-radius:5px; padding:7px; selection-background-color:#334f77; }
QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus { border-color:#8ab4ff; }
QComboBox { background:#142032; border:1px solid #2c3a50; border-radius:5px; padding:6px 8px; min-height:20px; }
QComboBox QAbstractItemView { background:#142032; selection-background-color:#334f77; }
QMenu { background:#162132; border:1px solid #34445c; padding:5px; }
QMenu::item { padding:7px 24px; }
QMenu::item:selected { background:#2a3a53; border-radius:3px; }
QToolTip { background:#223147; color:#edf2fa; border:1px solid #536886; padding:5px; }
QSplitter::handle { background:#1d2a3e; width:2px; }
QTabBar { background:#0e1725; }
QTabBar::tab { background:#111d2d; color:#aebbd0; padding:10px 14px; border-right:1px solid #26344a; }
QTabBar::tab:selected { background:#20324c; color:#edf3ff; border-bottom:2px solid #8ab4ff; }
QTabBar::tab:hover:!selected { background:#192a40; }
QScrollBar:vertical { background:transparent; width:9px; }
QScrollBar::handle:vertical { background:#34455f; border-radius:4px; min-height:24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QStatusBar { background:#101b2b; color:#a0afc4; border-top:1px solid #25334b; }
QDialog { background:#0e1725; }
QCheckBox { spacing:7px; padding:5px; }
QListWidget::item { padding:8px; }
QListWidget::item:selected { background:#294362; }
'''
COLOR_HTTP_OK = "#9ce0c4"
COLOR_HTTP_FAIL = "#f6a4b4"
COLOR_UNCHECKED = "#a0afc4"
