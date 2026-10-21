"""Build supplied SVG into PNG-compressed Windows ICO using Qt + stdlib.
Run from repository root with Python: tools/build_icon.py
"""
import struct
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

root = Path(__file__).resolve().parents[1]
assets = root / "ports" / "assets"
source = Path(r"D:\Downloads\localhost-port-reference-vector.svg")
assets.mkdir(exist_ok=True)
target = assets / "ports.svg"
if not target.exists():
    target.write_bytes(source.read_bytes())
app = QApplication([])
renderer = QSvgRenderer(str(target))
if not renderer.isValid():
    raise SystemExit("Invalid SVG")
images = []
for size in (16, 24, 32, 48, 64, 128, 256):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    images.append((size, bytes(buf.data())))
header = struct.pack("<HHH", 0, 1, len(images))
offset = 6 + len(images) * 16
entries, data = bytearray(), bytearray()
for size, png in images:
    entries.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
    data.extend(png)
    offset += len(png)
(assets / "ports.ico").write_bytes(header + entries + data)
print("Generated icon sizes:", [size for size, _ in images])
