"""Qt WebEngine terminal view hosting bundled xterm.js.

Backpressure: the PTY reader thread appends bytes to a bounded buffer; a UI
timer drains chunks to JS. If JS falls behind (>1 MiB in flight), the reader
blocks, which naturally throttles the PTY instead of dropping bytes.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from .stream_buffer import OutputBuffer

WEB_DIR = Path(__file__).parent / "web"
MAX_INFLIGHT = 1024 * 1024
CHUNK = 64 * 1024


class TerminalBridge(QObject):
    """Object exposed to JS as channel.objects.bridge."""

    output = pyqtSignal(str)         # base64 chunk for term.write
    clearScreen = pyqtSignal()
    setScrollback = pyqtSignal(int)
    scrollToBottom = pyqtSignal()

    inputReceived = pyqtSignal(str)      # decoded keystrokes -> PTY
    resizeReceived = pyqtSignal(int, int)
    urlOpenRequested = pyqtSignal(str)
    readyReceived = pyqtSignal()
    writtenReceived = pyqtSignal(int)
    searchResultReceived = pyqtSignal(int, int)
    scrolledUpReceived = pyqtSignal(bool)
    selectionCopied = pyqtSignal(str)

    @pyqtSlot(str)
    def input(self, b64: str) -> None:
        try:
            self.inputReceived.emit(
                base64.b64decode(b64).decode("utf-8", "replace"))
        except (ValueError, UnicodeDecodeError):
            pass

    @pyqtSlot(int, int)
    def resized(self, cols: int, rows: int) -> None:
        if 2 <= cols <= 1000 and 2 <= rows <= 1000:
            self.resizeReceived.emit(cols, rows)

    @pyqtSlot(str)
    def openUrl(self, url: str) -> None:
        self.urlOpenRequested.emit(url[:2048])

    @pyqtSlot()
    def ready(self) -> None:
        self.readyReceived.emit()

    @pyqtSlot(int)
    def written(self, n: int) -> None:
        self.writtenReceived.emit(n)

    @pyqtSlot(int, int)
    def searchResult(self, match: int, total: int) -> None:
        self.searchResultReceived.emit(max(0, match), max(0, total))

    @pyqtSlot(bool)
    def scrolledUp(self, value: bool) -> None:
        self.scrolledUpReceived.emit(bool(value))

    @pyqtSlot(str)
    def selectionCopy(self, text: str) -> None:
        self.selectionCopied.emit(text[:65536])

class LockedPage(QWebEnginePage):
    """Denies all navigation except the initial local terminal.html."""

    def __init__(self, allowed: QUrl, parent=None):
        super().__init__(parent)
        self._allowed = allowed
        self._loaded = False

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if not is_main_frame:
            return False
        if not self._loaded and url == self._allowed:
            self._loaded = True
            return True
        return False  # external links never navigate this page

    def createWindow(self, window_type):
        return None  # no popups


class TerminalView(QWebEngineView):
    """One durable terminal view; survives tab switches untouched."""

    inputReceived = pyqtSignal(str)
    resizeReceived = pyqtSignal(int, int)
    searchCountChanged = pyqtSignal(int, int)
    scrolledUpChanged = pyqtSignal(bool)
    selectionCopied = pyqtSignal(str)

    def __init__(self, scrollback: int = 10000, parent=None):
        super().__init__(parent)
        url = QUrl.fromLocalFile(str(WEB_DIR / "terminal.html"))
        self._page = LockedPage(url, self)
        self.setPage(self._page)
        self._font_size = 13
        settings = self._page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            False)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.PluginsEnabled, False)

        self.bridge = TerminalBridge(self)
        self._channel = QWebChannel(self._page)
        self._channel.registerObject("bridge", self.bridge)
        self._page.setWebChannel(self._channel)

        self.bridge.inputReceived.connect(self.inputReceived)
        self.bridge.resizeReceived.connect(self.resizeReceived)
        self.bridge.urlOpenRequested.connect(self._open_url)
        self.bridge.writtenReceived.connect(self._on_written)
        self.bridge.readyReceived.connect(self._on_ready)
        self.bridge.searchResultReceived.connect(self.searchCountChanged)
        self.bridge.scrolledUpReceived.connect(self.scrolledUpChanged)
        self.bridge.selectionCopied.connect(self.selectionCopied)

        self._scrollback = scrollback
        self._output_buffer = OutputBuffer()
        self._closing = False
        self._ready = False

        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(30)
        self._drain_timer.timeout.connect(self._drain)
        self._drain_timer.start()

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._page.load(url)

    # -- PTY -> JS (thread-safe entry from reader thread) ------------------

    def feed(self, data: bytes) -> None:
        self._output_buffer.put(data)

    def _drain(self) -> None:
        if self._ready and not self._closing:
            chunk = self._output_buffer.take(CHUNK)
            if chunk:
                self.bridge.output.emit(base64.b64encode(chunk).decode("ascii"))

    def _on_written(self, n: int) -> None:
        self._output_buffer.ack(n)

    def _on_ready(self) -> None:
        self._ready = True
        self.bridge.setScrollback.emit(self._scrollback)
        self.set_font_size(self._font_size)
        self.refit()

    def set_font_size(self, size: int) -> None:
        self._font_size = max(9, min(20, int(size)))
        if self._ready:
            self._page.runJavaScript(
                "window.__portsSetFontSize && window.__portsSetFontSize("
                f"{self._font_size})")

    # -- actions -------------------------------------------------------------

    def clear_terminal(self) -> None:
        self.bridge.clearScreen.emit()

    def search(self, needle: str, backwards: bool = False,
               incremental: bool = False) -> None:
        self._page.runJavaScript(
            "window.portsSearch && window.portsSearch("
            f"{json.dumps(needle)}, {str(backwards).lower()}, "
            f"{str(incremental).lower()})")

    def clear_search(self) -> None:
        self._page.runJavaScript(
            "window.portsClearSearch && window.portsClearSearch()")

    def scroll_to_bottom(self) -> None:
        self.bridge.scrollToBottom.emit()

    def refit(self) -> None:
        self._page.runJavaScript("window.portsFit && window.portsFit()")

    def focus_terminal(self) -> None:
        self.setFocus()
        self._page.runJavaScript("window.portsFocus && window.portsFocus()")

    def _open_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            QDesktopServices.openUrl(QUrl(url))

    def shutdown(self) -> None:
        self._closing = True
        self._output_buffer.close()
        self._drain_timer.stop()
