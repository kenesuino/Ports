"""Bundled action glyphs rendered with Qt; no font/network dependency."""
from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).parent / "assets"
_PATHS = {
    "terminal": '<path d="m4 6 5 6-5 6m9 0h7"/>',
    "workspace": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18M9 9v12"/>',
    "add": '<path d="M12 4v16M4 12h16"/>',
    "run": '<path d="m7 4 13 8-13 8z"/>',
    "restart": '<path d="M20 7v5h-5M19 12a7 7 0 1 0-2 5M20 12a8 8 0 0 0-3-6"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    "browser": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18"/>',
    "copy": '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    "settings": '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    "tabs": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M10 4v5M16 4v5"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "chevron": '<path d="m9 5 7 7-7 7"/>',
    "edit": '<path d="m15 4 5 5-11 11-6 1 1-6zM12 7l5 5"/>',
    "save": '<path d="M4 3h13l4 4v14H3V3h1M7 3v6h10V3M7 21v-8h10v8"/>',
    "folder": '<path d="M3 6h7l2 3h9v11H3z"/>',
    "retry": '<path d="M20 8v5h-5M20 12a8 8 0 1 0-3 6"/>',
}
_cache = {}


def icon(name, color="#aab8cc", size=20):
    key = (name, color, size)
    if key not in _cache:
        body = _PATHS.get(name, _PATHS["terminal"])
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
        painter.end()
        _cache[key] = QIcon(pixmap)
    return _cache[key]


def app_icon():
    return QIcon(str(ASSETS / "ports.ico"))
