"""Terminal pane: the WebEngine view with floating overlays positioned over it."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QTimer, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from .overlays import FailureOverlay, ScrollToBottomPill, SearchOverlay
from .theme import SPACE_2, SPACE_3

MARGIN = SPACE_3


class TerminalPane(QWidget):
    """Hosts one persistent terminal view plus its overlays.

    The view is never reparented, so switching tabs or toggling overlays keeps
    the xterm instance, scrollback and PTY untouched.
    """

    restartRequested = pyqtSignal()
    retryRequested = pyqtSignal()
    closeRequested = pyqtSignal(str)

    def __init__(self, session, scrollback: int = 10000, motion_disabled=False,
                 parent=None):
        super().__init__(parent)
        self.session = session
        self.motion_disabled = motion_disabled
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = None  # set by the caller after construction
        self.search = SearchOverlay(self)
        self.failure = FailureOverlay(self)
        self.pill = ScrollToBottomPill(self)

        self.search.queryChanged.connect(self._on_query)
        self.search.nextRequested.connect(lambda: self._step(False))
        self.search.previousRequested.connect(lambda: self._step(True))
        self.search.dismissed.connect(self.close_search)
        self.failure.restartRequested.connect(self.restartRequested)
        self.failure.retryRequested.connect(self.retryRequested)
        self.failure.closeRequested.connect(
            lambda: self.closeRequested.emit(self.session.id))
        self.pill.clicked.connect(self._scroll_bottom)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(30)
        self._resize_timer.timeout.connect(self._layout_overlays)

    def attach_view(self, view) -> None:
        self.view = view
        self.layout().addWidget(view)
        view.installEventFilter(self)
        view.searchCountChanged.connect(self._on_count)
        view.scrolledUpChanged.connect(self._on_scrolled)
        view.setFocusPolicy(view.focusPolicy())
        # Overlays must sit above the web view in z-order.
        self.search.raise_()
        self.failure.raise_()
        self.pill.raise_()
        self._resize_timer.start()

    # -- search ---------------------------------------------------------

    def open_search(self) -> None:
        if self.view is None:
            return
        self.search.open()

    def close_search(self) -> None:
        self.search.close_search()
        if self.view is not None:
            self.view.clear_search()
            self.view.focus_terminal()

    def _on_query(self, text: str) -> None:
        if self.view is None:
            return
        if not text:
            self.view.clear_search()
            return
        self.view.search(text, False, incremental=True)

    def _step(self, backwards: bool) -> None:
        if self.view is None:
            return
        text = self.search.field.text()
        if text:
            self.view.search(text, backwards, incremental=False)

    def _on_count(self, match: int, total: int) -> None:
        self.search.set_count(match, total)

    # -- scroll pill ----------------------------------------------------

    def _on_scrolled(self, value: bool) -> None:
        self.pill.set_scrolled_up(value, self.motion_disabled)

    def _scroll_bottom(self) -> None:
        if self.view is not None:
            self.view.scroll_to_bottom()
        self.pill.setVisible(False)

    # -- failure --------------------------------------------------------

    def sync_failure(self) -> None:
        if self.session.state in ("failed", "exited"):
            self.failure.show_failure(self.session, self.motion_disabled)
        else:
            self.failure.hide_overlay()

    # -- geometry -------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.view and event.type() == QEvent.Type.Resize:
            self._resize_timer.start()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_overlays()

    def _layout_overlays(self) -> None:
        width, height = self.width(), self.height()
        if width <= 0 or height <= 0:
            return
        self.search.adjustSize()
        self.search.move(max(MARGIN, width - self.search.width() - MARGIN),
                         MARGIN)
        self.failure.adjustSize()
        self.failure.setFixedWidth(min(460, max(280, width - MARGIN * 2)))
        self.failure.move(MARGIN, MARGIN)
        self.pill.adjustSize()
        self.pill.move(max(MARGIN, (width - self.pill.width()) // 2),
                       max(MARGIN, height - self.pill.height() - SPACE_2))
        self.search.raise_()
        self.failure.raise_()
        self.pill.raise_()
