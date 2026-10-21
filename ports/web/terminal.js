/* Ports terminal bridge: xterm.js <-> Qt WebChannel <-> Python PtySession.
 *
 * Python -> JS: bridge.output(base64) chunks, acked via bridge.written().
 * JS -> Python: bridge.input(base64), bridge.resized(cols, rows),
 *               bridge.openUrl(url), bridge.ready().
 */
(function () {
  "use strict";

  var MAX_INFLIGHT = 1024 * 1024; // must mirror Python side

  function b64encode(str) {
    return btoa(unescape(encodeURIComponent(str)));
  }
  function b64decode(b64) {
    return decodeURIComponent(escape(atob(b64)));
  }

  var term = new Terminal({
    fontFamily: "'Cascadia Code', 'Cascadia Mono', Consolas, monospace",
    fontSize: 13,
    cursorBlink: true,
    scrollback: 10000,
    allowProposedApi: true,
    theme: {
      background: "#0b0e14",
      foreground: "#d5dbe5",
      cursor: "#7aa2f7",
      cursorAccent: "#0b0e14",
      selectionBackground: "#31456b",
      black: "#1a1f2b", red: "#f7768e", green: "#9ece6a",
      yellow: "#e0af68", blue: "#7aa2f7", magenta: "#bb9af7",
      cyan: "#7dcfff", white: "#d5dbe5",
      brightBlack: "#414868", brightRed: "#f7768e", brightGreen: "#9ece6a",
      brightYellow: "#e0af68", brightBlue: "#7aa2f7",
      brightMagenta: "#bb9af7", brightCyan: "#7dcfff", brightWhite: "#ffffff"
    }
  });

  var fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  var searchAddon = new SearchAddon.SearchAddon();
  term.loadAddon(searchAddon);

  var bridge = null;

  // URLs are validated + opened by Python, never by the web view itself.
  var webLinks = new WebLinksAddon.WebLinksAddon(function (event, uri) {
    if (bridge) bridge.openUrl(uri);
  });
  term.loadAddon(webLinks);

  term.open(document.getElementById("terminal"));
  fitAddon.fit();

  // Write queue with ack-based backpressure toward Python.
  var queue = [];
  var writing = false;
  function pump() {
    if (writing || queue.length === 0) return;
    writing = true;
    var chunk = queue.shift();
    term.write(b64decode(chunk), function () {
      writing = false;
      if (bridge) bridge.written(chunk.length);
      pump();
    });
  }

  function connect(channel) {
    bridge = channel.objects.bridge;
    bridge.output.connect(function (b64) {
      queue.push(b64);
      pump();
    });
    bridge.clearScreen.connect(function () {
      term.clear();
      term.reset();
    });
    bridge.setScrollback.connect(function (lines) {
      term.options.scrollback = lines;
    });
    bridge.ready();
  }

  term.onData(function (data) {
    if (bridge) bridge.input(b64encode(data));
  });
  term.onResize(function (size) {
    if (bridge) bridge.resized(size.cols, size.rows);
  });

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { fitAddon.fit(); }, 60);
  });

  // Exposed for Python-invoked search.
  window.portsSearch = function (needle, backwards) {
    return backwards
      ? searchAddon.findPrevious(needle)
      : searchAddon.findNext(needle);
  };
  window.portsFit = function () { fitAddon.fit(); };
  window.portsFocus = function () { term.focus(); };

  new QWebChannel(qt.webChannelTransport, connect);
})();
