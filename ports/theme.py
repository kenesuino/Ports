"""Neutral gray design tokens and the Qt stylesheet.

One low-chroma palette: near-black canvas, single green accent for listening
state, red reserved for destructive actions, amber for waiting/failed.
Hierarchy comes from the type scale and spacing, not from boxes or glows.
"""

# Surfaces (exactly neutral: no blue cast)
CANVAS = "#0e0e0e"
PANEL = "#151515"
RAISED = "#1b1b1b"
HOVER = "#202020"
PRESSED = "#272727"
BORDER = "#282828"
DIVIDER = "#212121"

# Text
TEXT = "#e7e7e7"
TEXT_SECONDARY = "#b4b4b4"
TEXT_MUTED = "#8e8e8e"
TEXT_DISABLED = "#5d5d5d"

# Semantic
LISTENING = "#4fd18b"
DESTRUCTIVE = "#ff7b8a"
WAITING = "#d9a441"
FOCUS = "#c8c8c8"

# Motion, milliseconds. One out-cubic curve shared by QSS and Qt animations.
MOTION_FAST = 120
MOTION_PANEL = 180
MOTION_TOAST = 240
EASING = (0.23, 1.0, 0.32, 1.0)

# Spacing scale
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_5, SPACE_6 = 4, 8, 12, 16, 20, 24

# Type scale
FONT_LABEL = "font-size:11px;"
FONT_BODY = "font-size:12px;"
FONT_CONTROL = "font-size:13px;"
FONT_TITLE = "font-size:15px; font-weight:600;"
UI_FONT = '"Segoe UI", "Segoe UI Variable", sans-serif'
MONO_FONT = '"Cascadia Mono", Consolas, monospace'

# Backwards-compatible names used by earlier modules.
COLOR_HTTP_OK = LISTENING
COLOR_HTTP_FAIL = DESTRUCTIVE
COLOR_UNCHECKED = TEXT_MUTED

QSS = f"""
QMainWindow {{ background: {CANVAS}; }}
QWidget {{ color: {TEXT}; font-family: {UI_FONT}; {FONT_BODY} }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {TEXT_MUTED}; {FONT_BODY} }}
QLabel#mono {{ font-family: {MONO_FONT}; {FONT_BODY} color: {TEXT_SECONDARY}; }}
QLabel#brand {{ {FONT_TITLE} letter-spacing: 1px; }}
QLabel#emptyTitle {{ {FONT_TITLE} color: {TEXT}; }}
QLabel#emptyBody {{ color: {TEXT_SECONDARY}; {FONT_CONTROL} }}
QLabel#sectionLabel {{
    color: {TEXT_MUTED}; {FONT_LABEL}
    padding: 2px 0 0 0;
}}

QWidget#rail {{ background: {PANEL}; }}
QWidget#workspace {{ background: {CANVAS}; }}
QWidget#header {{ background: {PANEL}; }}
QWidget#footer {{ background: {PANEL}; }}
QWidget#portsInspector {{ background: {PANEL}; }}
QWidget#tabStrip {{ background: {CANVAS}; }}
QLabel#footerText {{ color: {TEXT_MUTED}; {FONT_LABEL} }}
QFrame#divider {{ background: {DIVIDER}; border: none; }}

QPushButton {{
    background: {RAISED}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 5px 10px; color: {TEXT}; {FONT_CONTROL}
}}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {PRESSED}; }}
QPushButton:disabled {{ color: {TEXT_DISABLED}; background: {PANEL}; border-color: {DIVIDER}; }}
QPushButton:focus {{ border-color: {FOCUS}; }}
QPushButton#primary {{ background: {TEXT}; color: {CANVAS}; border-color: {TEXT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: #f3f5f8; }}
QPushButton#primary:disabled {{ background: {RAISED}; color: {TEXT_DISABLED}; border-color: {BORDER}; }}
QPushButton#iconBtn {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    padding: 2px; min-width: 26px; min-height: 26px;
}}
QPushButton#iconBtn:hover {{ background: {HOVER}; border-color: {BORDER}; }}
QPushButton#iconBtn:pressed {{ background: {PRESSED}; }}
QPushButton#danger {{ color: {DESTRUCTIVE}; border-color: #4a2b31; background: #1e1618; }}
QPushButton#danger:hover {{ background: #2a1d21; }}
QPushButton#chip {{
    background: transparent; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 2px 8px; color: {LISTENING};
    font-family: {MONO_FONT}; {FONT_BODY}
}}
QPushButton#chip:hover {{ background: {RAISED}; border-color: #3a4149; }}
QPushButton#ghostChip {{
    background: transparent; border: 1px dashed #353b43; border-radius: 10px;
    padding: 2px 8px; color: {TEXT_DISABLED};
    font-family: {MONO_FONT}; {FONT_BODY}
}}
QPushButton#statusPill {{
    background: {RAISED}; border: 1px solid {BORDER}; border-radius: 11px;
    padding: 3px 10px; color: {TEXT_SECONDARY}; {FONT_BODY}
}}
QPushButton#statusPill:hover {{ background: {HOVER}; }}
QPushButton#rowAction {{
    background: transparent; border: none; padding: 2px; border-radius: 4px;
}}
QPushButton#rowAction:hover {{ background: {HOVER}; }}

QPushButton#groupHeader, QPushButton#ownerHeader {{
    background: transparent; border: none; border-bottom: 1px solid {DIVIDER};
    color: {TEXT_MUTED}; {FONT_LABEL}
    text-align: left; padding: 6px 2px 5px 2px; margin: 2px 0 4px 0;
}}
QPushButton#groupHeader:hover, QPushButton#ownerHeader:hover {{
    color: {TEXT_SECONDARY}; background: {RAISED};
}}
QPushButton#groupHeader:focus, QPushButton#ownerHeader:focus {{
    color: {TEXT}; border-bottom: 1px solid {FOCUS};
}}

QLineEdit, QPlainTextEdit, QListWidget {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 8px; color: {TEXT};
    selection-background-color: #3a4048; selection-color: {TEXT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus {{ border-color: {FOCUS}; }}
QComboBox {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 8px; min-height: 20px;
}}
QComboBox:hover {{ border-color: #3a4149; background: {RAISED}; }}
QComboBox:focus {{ border-color: {FOCUS}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: none; width: 12px; height: 12px; margin-right: 5px; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {BORDER};
    selection-background-color: {HOVER}; selection-color: {TEXT};
    padding: 4px; outline: none;
}}
QComboBox QAbstractItemView::item {{ padding: 7px 10px; border-radius: 4px; min-height: 20px; }}

QPushButton#railAction {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    padding: 7px 10px; color: {TEXT_SECONDARY}; text-align: left;
}}
QPushButton#railAction:hover {{ background: {RAISED}; color: {TEXT}; border-color: {BORDER}; }}
QPushButton#railAction:pressed {{ background: {PRESSED}; }}
QPushButton#railAction:focus {{ border-color: {FOCUS}; }}

QTabBar[overflow="true"] {{
    border-left: 1px solid {DIVIDER};
    border-right: 1px solid {DIVIDER};
}}
QTabBar::scroller {{ width: 18px; }}
QTabBar QToolButton {{
    background: {RAISED}; border: none; border-radius: 4px;
    color: {TEXT_MUTED};
}}
QTabBar QToolButton:hover {{ background: {HOVER}; color: {TEXT}; }}

QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_MUTED};
    padding: 7px 14px; margin-right: 2px; border: none;
    border-bottom: 2px solid transparent; {FONT_BODY}
}}
QTabBar::tab:hover:!selected {{ color: {TEXT_SECONDARY}; background: #1a1a1a; }}
QTabBar::tab:selected {{
    color: {TEXT}; background: {RAISED}; border-bottom: 2px solid {TEXT};
}}

QMenu {{
    background: {RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px;
}}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::separator {{ height: 1px; background: {DIVIDER}; margin: 4px 6px; }}
QMenu::item:disabled {{ color: {TEXT_MUTED}; }}

QToolTip {{
    background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 4px 6px; {FONT_BODY}
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: #2a2e35; border-radius: 3px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: #4a5058; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{
    background: #2a2e35; border-radius: 3px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: #4a5058; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QDialog {{ background: {PANEL}; }}
QCheckBox {{ spacing: 6px; }}
QCheckBox:focus {{ color: {TEXT}; }}
QListWidget::item {{ padding: 6px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {HOVER}; color: {TEXT}; }}

QSplitter::handle {{ background: {DIVIDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QStatusBar {{ background: {PANEL}; color: {TEXT_MUTED}; border-top: 1px solid {DIVIDER}; }}
"""
