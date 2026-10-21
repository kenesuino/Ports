import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication


def main():
    # Rasterize screenshots for inspection without changing their evidence.
    app = QApplication(['ports-capture-review'])
    folder = Path(__file__).resolve().parents[1] / 'artifacts'
    for path in folder.glob('*.png'):
        if path.name.startswith('review-'):
            continue
        pixmap = QPixmap(str(path))
        pixmap.scaledToWidth(1100, Qt.TransformationMode.SmoothTransformation).save(str(folder / ('review-' + path.name)))


if __name__ == '__main__':
    main()
