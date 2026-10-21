# Ports

Native Windows terminal manager with reusable workspace profiles, persistent
interactive ConPTY terminals, and localhost listener ownership.

## Run

```powershell
cd F:\Github\Ports
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m ports
```

Python 3.11+; tested here on Windows 10.0.26300, Python 3.13.5, Qt 6.11.2,
PyQt6/PyQt6-WebEngine 6.11.0, pywinpty 3.1.0 and psutil 7.2.2.
PowerShell 7 is optional: install `pwsh.exe` separately if wanted. Windows
PowerShell, CMD and WSL are discovered from PATH. WSL tracking requires
`python3` and `ss` (`iproute2`) in the selected distribution.

## Workspace profiles

Use workspace actions beside the profile selector to create/edit a profile,
save currently open terminals, duplicate or delete definitions. Each terminal
stores name, shell/distro, folder, explicit startup/restart commands, accent,
and optional expected ports. Commands can contain secrets: avoid saving them;
this config is local JSON, not a credential store.

- **Run workspace** reviews executable settings on first run or after shell,
  folder, command or terminal-definition changes. Cosmetic changes do not
  invalidate review. Run focuses an existing instance instead of duplicating it.
- **Launch another copy** is explicit and warns about port conflicts.
- **Restore missing terminals** starts only absent members; **Retry failed
  launch** is available from the session-card menu. Successful peers remain open.
- Layout restore opens fresh shells without executing saved commands. Command
  definitions remain available for explicit restart.
- Editing a profile never changes commands already running in its instances.

## Navigation and controls

Header selector switches between sidebar cards and top tabs without recreating
terminal views or processes. Double-click a card/tab to rename. Tabs drag to
reorder; sidebar menus offer Move up/down. Port chips open loopback HTTP URLs;
right-click for Copy URL, labels, optional HTTP checks and confirmed termination.
External listeners remain available in both layouts. Preferences edits external
process filters and reduced motion. Exact port search bypasses display filters.

Shortcuts: Ctrl+Shift+T new terminal, Ctrl+Shift+F buffer search, Ctrl+Tab /
Ctrl+Shift+Tab next/previous session, Ctrl+W close with confirmation.

Shell readiness hooks support Windows PowerShell/PowerShell 7 and WSL Bash.
Startup runs once after a prompt marker, not after an arbitrary timer. Typing
cancels pending startup/restart. CMD restart explicitly asks you to confirm
prompt readiness. Automatic restart uses only saved commands, never Up+Enter.
Live folder display is updated by supported hooks; fallback says Starting folder.

## Persistence and recovery

`%APPDATA%/Ports/config.json` stores profiles, stable label scopes, layout,
window/splitter state and filters. Version 1 config migrates on successful save.
Unreadable/newer/oversized config remains untouched and read-only; Preferences
can explicitly create a recovery backup and enable save. Save uses same-directory
atomic replacement. Stored layout does not reattach running processes.

## Safety and limits

- Force kill on Windows is forceful, not graceful termination. Owner PID/start
  identity and selected endpoint are checked again before acting. Session roots
  and critical processes are protected. Watchers may restart killed workers.
- WSL signals validate positive PID, Linux start identity and socket ownership;
  helper acknowledgements report refusal/failure. External listeners cannot be
  controlled if their owner is inaccessible. WSL distribution identity stays
  separate; same-numbered forwarder sockets are not silently merged.
- Windows job assignment precedes user shell startup through a bootstrap event.
  Assignment failures surface as reduced-confidence fallback. Polling cannot
  reconstruct parents that disappeared before observation outside job membership.
- Port scans and process waits run outside GUI thread; failures mark data stale.
  HTTP probes use bounded workers and deadlines; timeout/refused/not-HTTP are
  observations, not health claims. Probes are opt-in.
- Terminal bridge uses a 1 MiB byte-accounted queue and preserves UTF-8 across
  writes. Retained scrollback defaults to 10,000 lines. Clear removes scrollback
  without resetting running terminal modes.
- WSL close requests SIGHUP for its identity-verified shell; detached/disowned
  Linux processes may survive. Universal detached-tree cleanup is not guaranteed.
- Imported configurations are local trusted settings, not cryptographic command
  authorization. Prompt markers are metadata, not a security boundary against a
  malicious same-user process.

## Appearance and assets

Supplied `localhost-port-reference-vector.svg` is preserved as
`ports/assets/ports.svg`; generated multi-size ICO is packaged for title/taskbar.
`tools/build_icon.py` rebuilds it with Qt and stdlib. Action glyphs use consistent
Qt-rendered SVG strokes. Windows native title controls remain intact. Header
uses session accent; 120 ms hover and 180 ms drawer transitions honor reduced
motion. No terminal-output or tab-switch animations.

Qt WebEngine uses local bundled xterm.js, not CDN assets. See
`ports/web/vendor/VERSIONS.txt` and `THIRD_PARTY_NOTICES.md`. PyQt6 is GPL/commercial;
check distribution obligations before shipping under incompatible terms.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe tools/desktop_check.py
.\.venv\Scripts\python.exe tools/desktop_check.py --width 1024 --scale 1.5
```

Regression suite covers config/profile migration and review invalidation,
readiness parser, real PowerShell startup, Windows ConPTY/job processes,
listener attribution, identity refusal, WSL listener/signal integration,
stream-byte bounds, view model and probes. WSL tests skip without configured
Ubuntu. Passing skipped checks is not WSL evidence.

Desktop checker isolates config and starts only its own three-terminal workspace.
It verifies actual WebEngine bridge readiness and displayed `PORTS_RENDER_OK`,
then captures both views into `artifacts/`. Qt needs a program-name argument;
`QApplication([])` causes native WebEngine abort and is not a valid rendering test.
On this machine WebEngine DOM/output checks passed at 100/150/200% configured
scales, but GPU/context diagnostics and screenshot artifacts prevent a full visual
sign-off. Actual keyboard/IME, taskbar icon and screen-reader behavior still need
interactive hardware validation; unit tests do not establish those passes.
