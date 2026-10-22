"""Later column painting must preserve the selected workspace label."""
import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem

from ports.theme import CANVAS, TEXT
from ports.tree_delegate import TreeDelegate


@pytest.mark.parametrize('focused', [False, True])
def test_selected_workspace_label_survives_duration_column(qt_application, focused):
    tree = QTreeWidget()
    tree.setColumnCount(2)
    tree.resize(320, 100)
    item = QTreeWidgetItem(tree, ['Smart Driving App', ''])
    tree.setCurrentItem(item)
    delegate = TreeDelegate(tree)
    image = QImage(320, 34, QImage.Format.Format_ARGB32)
    image.fill(QColor(CANVAS))
    painter = QPainter(image)
    try:
        for column, rect in enumerate((QRect(12, 0, 242, 34), QRect(254, 0, 66, 34))):
            option = QStyleOptionViewItem()
            option.widget = tree
            option.rect = rect
            option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected
            if focused:
                option.state |= QStyle.StateFlag.State_HasFocus
            delegate.paint(painter, option, tree.indexFromItem(item, column))
    finally:
        painter.end()
    assert any(image.pixelColor(x, y) == QColor(TEXT)
               for x in range(20, 230) for y in range(5, 29)), 'Workspace label was painted over'
