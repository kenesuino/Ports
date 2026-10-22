"""Bundled action glyphs rendered with Qt; no font or network dependency."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).parent / "assets"
STROKE = "#b9c0ca"
SIZE = 18

# One consistent stroke weight; geometry drawn on a 24px grid.
_PATHS = {
    "terminal": '<path d="m4 7 5 5-5 5m8 0h8"/>',
    "workspace": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18M9 9v12"/>',
    "add": '<path d="M12 5v14M5 12h14"/>',
    "run": '<path d="m8 5 11 7-11 7z"/>',
    "restart": '<path d="M20 7v5h-5M20 12a8 8 0 1 0-2.4 5.7"/>',
    "kill": '<path d="M8 3h8l5 5v8l-5 5H8l-5-5V8zM9 9l6 6m0-6-6 6"/>',
    "clear": '<path d="m15 3-6 8m-3 0 7 5m-7-5-4 7 8 4 3-6M5 15l5 3M17 18h5m-7 4h5"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/>',
    "browser": '<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4a14 14 0 0 1 0 16 14 14 0 0 1 0-16"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/>',
    "settings": '<path d="M4 7h9M4 17h5"/><circle cx="17" cy="7" r="3"/><circle cx="11" cy="17" r="3"/>',
    "close": '<path d="m7 7 10 10M17 7 7 17"/>',
    "chevron": '<path d="m9 6 6 6-6 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "edit": '<path d="m15 4 5 5-11 11H4v-5z"/>',
    "save": '<path d="M5 3h11l3 3v15H5zM8 3v6h8V3M8 21v-7h8v7"/>',
    "folder": '<path d="M3 6h7l2 3h9v11H3z"/>',
    "open-folder": '<path d="M3 7h6l2 3h10v3M3 7v11h13l4-7"/>',
    "copy-path": '<path d="M4 6h9M4 10h6M4 14h5"/><rect x="12" y="11" width="9" height="9" rx="2"/>',
    "retry": '<path d="M20 9v5h-5M20 14a8 8 0 1 1-2.3-6"/>',
    "plug": '<path d="M9 3v6M15 3v6M6 9h12v3a6 6 0 0 1-12 0zM12 18v3"/>',
    "power": '<path d="M12 4v8M7.5 7a7 7 0 1 0 9 0"/>',
    "layout": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    "keyboard": '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8"/>',
}

_cache: dict[tuple[str, str, int], QIcon] = {}
_brand_cache: dict[int, QPixmap] = {}


def brand_mark(size: int = 18) -> QPixmap:
    """Render the supplied product SVG at a fixed size for the rail header."""
    cached = _brand_cache.get(size)
    if cached is not None:
        return cached
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(ASSETS / "ports.svg"))
    if renderer.isValid():
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
    _brand_cache[size] = pixmap
    return pixmap


def icon(name: str, color: str | None = None, size: int = SIZE) -> QIcon:
    color = color or STROKE
    key = (name, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    body = _PATHS.get(name, _PATHS["terminal"])
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" stroke="' + color + '" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        + body + "</svg>"
    )
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    result = QIcon(pixmap)
    _cache[key] = result
    return result


def app_icon() -> QIcon:
    return QIcon(str(ASSETS / "ports.ico"))
