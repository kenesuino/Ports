# Ports

Dark-mode Windows developer command center: interactive multi-shell terminal
tabs (PowerShell 7, Windows PowerShell, CMD, WSL) with automatic,
descendant-aware localhost port detection and one-click port/process control.

## Features

- True interactive ConPTY terminals rendered by bundled xterm.js: full
  keyboard input, `[y/N]` prompts, Ctrl+C, arrow history, tab completion,
  ANSI colors, full-screen apps, Unicode. Tab switches preserve screen and
  retained scrollback (default 10,000 lines, configurable).
- Windows descendant tracking via Job Objects: child and grandchild
  processes survive intermediate-parent exit and stay attributed to the
  owning session.
- Full WSL tracking via a stdlib-only Linux helper: Linux-side process tree,
  socket ownership (IPv4 + IPv6), and signals. Windows `wslrelay`/`wslhost`
  forwarder duplicates are merged, not double-counted.
- Port badges on each session card: click to open `http://localhost:<port>`,
  right-click for Open / Edit label / Kill owner (identity-verified).
- External ports panel: listeners outside Ports, with noise filtering that
  never hides session-owned ports or exact search results.
- Find port: type a port number, see PID/name/cmdline, kill with one click.
- Safe Restart: sends Ctrl+C, waits for descendants to exit, re-runs the
  session's recorded startup command. Never blind Up+Enter replay. Sessions
  without a startup command have Restart disabled with an explanation.
- Kill confirmation dialog for every destructive action, showing PID, name,
  redacted command line, and environment. PID + creation-time identity is
  revalidated immediately before acting; recycled PIDs are refused.
- Optional per-badge HTTP checks (response status vs refused/timeout/not
  HTTP), port labels, session-layout restore on launch (fresh shells;
  startup commands never auto-replay), graceful shutdown confirmation.

## Requirements

- Windows 10/11 (ConPTY; 1809+)
- Python 3.11+ (tested on 3.13.5)
- For WSL tracking: a running WSL2 distribution with `python3` and `ss`
  (iproute2). Tested: Ubuntu with Python 3.12.3. Ports runs unelevated;
  inaccessible owners are shown as unknown, never fabricated.

## Install and run

```powershell
git clone <repo> F:\Github\Ports
cd F:\Github\Ports
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m ports
```

Pinned runtime deps: PyQt6 6.11.0, PyQt6-WebEngine 6.11.0, pywinpty 3.1.0,
psutil 7.2.2. Frontend assets (xterm.js 5.5.0 + addons) are vendored under
`ports/web/vendor/`; see `ports/web/vendor/VERSIONS.txt` to rebuild.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Suite covers config persistence, port mapping/noise filtering, identity-safe
kills, HTTP probing, ConPTY smoke (echo/Ctrl+C/job tracking), a full
Windows end-to-end cycle (server spawned in-session -> attributed -> killed
-> shell survives), and a live WSL attribution + signal test (skipped when
no suitable distro exists).

## Security model

- Qt WebEngine loads only bundled local assets; navigation and popups are
  blocked; terminal output is treated as data, never HTML/JS.
- URL opening is validated (http/https only) and always user-initiated.
- Command lines shown in dialogs are credential-redacted.
- Wildcard (`0.0.0.0`/`::`) listeners are badged as potentially
  LAN-reachable (subject to firewall).

## Known constraints

- Header shows the session's starting folder; live directory tracking via
  shell integration hooks is not implemented (CMD has no reliable hook).
- HTTP checks distinguish response status / refused / timeout / not-HTTP;
  they do not assert service health. On this Windows build, loopback
  connection refusal with a connect timeout surfaces as bare `TimeoutError`;
  Ports connects without a timeout first (safe on loopback) to report
  refusals accurately.
- WSL attribution requires the helper channel; if the distro lacks python3
  or iproute2, the session shows interactive-only with an actionable error.

## Licensing

PyQt6 is GPL/commercial. Distributing this application under terms
incompatible with the GPL requires a commercial PyQt license. See
THIRD_PARTY_NOTICES.md.
