/* Ports terminal bridge: xterm.js <-> Qt WebChannel <-> Python PtySession.
 *
 * Python -> JS: bridge.output(base64) chunks, acked via bridge.written(bytes).
 * JS -> Python: bridge.input(base64), bridge.resized(cols, rows),
 *               bridge.openUrl(url), bridge.searchResult(match, total),
 *               bridge.scrolledUp(bool), bridge.ready().
 */
(function () {
  "use strict";

  function b64encode(str) {
    return btoa(unescape(encodeURIComponent(str)));
  }
  function b64decode(b64) {
    var text = atob(b64);
    var bytes = new Uint8Array(text.length);
    for (var i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
    return bytes;
  }

  var term = new Terminal({
    fontFamily: "'Cascadia Mono', 'Cascadia Code', Consolas, monospace",
    fontSize: 13,
    lineHeight: 1.2,
    cursorBlink: true,
    cursorStyle: "bar",
    scrollback: 10000,
    smoothScrollDuration: 80,
    rightClickSelectsWord: true,
    allowProposedApi: true,
    theme: {
      background: "#0f0f0f",
      foreground: "#e7e7e7",
      cursor: "#d8d8d8",
      cursorAccent: "#0f0f0f",
      selectionBackground: "#3b3b3b",
      black: "#1c1c1c", red: "#ff7b8a", green: "#4fd18b",
      yellow: "#d9a441", blue: "#a8b4c2", magenta: "#c0a8c8",
      cyan: "#8fc7c2", white: "#e7e7e7",
      brightBlack: "#5d5d5d", brightRed: "#ff93a0", brightGreen: "#6fdfa2",
      brightYellow: "#e8b95c", brightBlue: "#c2ccd8", brightMagenta: "#d4c0da",
      brightCyan: "#a5d8d2", brightWhite: "#f8f8f8"
    }
  });

  var fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.options.screenReaderMode = true;
  var searchAddon = new SearchAddon.SearchAddon();
  term.loadAddon(searchAddon);

  var bridge = null;
  var totalMatches = 0;
  var matchIndex = 0;

  // URLs are validated and opened by Python, never by the web view itself.
  var webLinks = new WebLinksAddon.WebLinksAddon(function (event, uri) {
    if (bridge) bridge.openUrl(uri);
  });
  term.loadAddon(webLinks);

  term.open(document.getElementById("terminal"));
  fitAddon.fit();

  var queue = [];
  var writing = false;
  function pump() {
    if (writing || queue.length === 0) return;
    writing = true;
    var chunk = queue.shift();
    var bytes = b64decode(chunk);
    term.write(bytes, function () {
      writing = false;
      if (bridge) bridge.written(bytes.length);
      pump();
    });
  }

  function reportScroll() {
    if (!bridge) return;
    var buffer = term.buffer.active;
    bridge.scrolledUp(buffer.viewportY < buffer.baseY);
  }

  term.onScroll(reportScroll);

  function connect(channel) {
    bridge = channel.objects.bridge;
    bridge.output.connect(function (b64) {
      queue.push(b64);
      pump();
    });
    bridge.clearScreen.connect(function () {
      term.clear();
    });
    bridge.setScrollback.connect(function (lines) {
      term.options.scrollback = lines;
    });
    bridge.scrollToBottom.connect(function () {
      term.scrollToBottom();
    });
    bridge.ready();
    term.focus();
    requestAnimationFrame(function () {
      fitAddon.fit();
      bridge.resized(term.cols, term.rows);
    });
  }

    term.onData(function (data) {
    if (bridge) bridge.input(b64encode(data));
  });

  // Copy-on-select: mirror a finished selection to the Python clipboard.
  // xterm exposes no mouseup event, so listen on the document and check for a
  // live selection after the drag completes.
  function copySelection() {
    if (!bridge || !term.hasSelection()) return;
    var text = term.getSelection();
    if (text) bridge.selectionCopy(text);
  }
  document.addEventListener("mouseup", function (event) {
    if (event.button === 0) setTimeout(copySelection, 0);
  });
  term.onResize(function (size) {
    if (bridge) bridge.resized(size.cols, size.rows);
  });

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { fitAddon.fit(); }, 60);
  });

  function reportMatches(value) {
    if (!bridge) return;
    totalMatches = (value && value.resultIndex !== undefined)
      ? searchAddon.searchResults ? searchAddon.searchResults.length : 0
      : 0;
    if (!value || value.resultIndex === undefined) {
      bridge.searchResult(0, 0);
      return;
    }
    matchIndex = value.resultIndex + 1;
    bridge.searchResult(matchIndex, totalMatches || matchIndex);
  }

  window.portsSearch = function (needle, backwards, incremental) {
    if (!needle) {
      searchAddon.clearDecorations();
      if (bridge) bridge.searchResult(0, 0);
      return false;
    }
    var options = { incremental: !!incremental, decorations: {} };
    return backwards
      ? searchAddon.findPrevious(needle, options, reportMatches)
      : searchAddon.findNext(needle, options, reportMatches);
  };

  window.portsClearSearch = function () {
    searchAddon.clearDecorations();
    if (bridge) bridge.searchResult(0, 0);
  };

  window.portsFit = function () {
    fitAddon.fit();
    if (bridge) bridge.resized(term.cols, term.rows);
  };

  window.portsBufferText = function () {
    var lines = [];
    var buffer = term.buffer.active;
    for (var i = 0; i < buffer.length; i++) {
      lines.push(buffer.getLine(i).translateToString(true));
    }
    return lines.join("\n");
  };

  window.portsFocus = function () { term.focus(); };

  window.__portsSetFontSize = function (size) {
    var clamped = Math.max(9, Math.min(20, size | 0));
    term.options.fontSize = clamped;
    requestAnimationFrame(function () {
      fitAddon.fit();
      if (bridge) bridge.resized(term.cols, term.rows);
    });
  };

  new QWebChannel(qt.webChannelTransport, connect);
})();
