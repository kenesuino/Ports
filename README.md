# Ports

Windows desktop terminal manager with remembered workspace navigation, true
interactive ConPTY sessions, and descendant-aware localhost port control.

## Run

```powershell
cd F:\Github\Ports
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m ports
```

Python 3.11+, tested with Python 3.13.5, PyQt6/PyQt6-WebEngine 6.11.0,
Qt 6.11.2, pywinpty 3.1.0, psutil 7.2.2 on Windows build 26300. PowerShell 7
is optional; Windows PowerShell, CMD and WSL are also supported. WSL requires
`python3` and `ss` (iproute2) in its selected distribution.

## Workspace navigation

**Left:** an always-expanded, resizable workspace tree (minimum 220px). Workspace
groups expand/collapse, but the sidebar never changes to an icon strip.
Choose a saved profile and click **Load workspace**. Its definitions appear
immediately; loading does not start any shell or command. The sidebar remembers
loaded profiles, order, expansion and last selected workspace across launches.
**New workspace** and **Manage saved profiles** create/edit/delete definitions.
Profile deletion stays separate from **Remove workspace from sidebar**, which
only unpins: profiles and running sessions remain untouched.

Running sessions of an unpinned/deleted workspace stay reachable under **Other
terminals**. Loading the profile again reconnects its existing sessions, not
copies. Ad-hoc New terminal sessions belong to the selected workspace instance;
when created in Other terminals they remain unassigned until saved explicitly.

Each terminal has its own **Start** action. Hover a terminal row (or focus it by
keyboard) to reveal Start/Edit for stopped definitions, Close/Rename for live
sessions, and Retry for failed/exited shells. Row actions stay inside the tree
viewport and act on that row rather than whichever terminal was previously
selected. The bottom action bar and context menu remain keyboard alternatives.
Selecting a stopped definition stays selected across refreshes, including in the
first workspace; it does not launch the shell or switch to another definition.

Select a definition and use the
Start button or context menu; only that terminal starts, after executable-setting
review when needed. Repeat Start focuses an existing launch rather than duplicating
it. Context-menu **Start another copy of this terminal** explicitly creates a new
instance containing just that terminal. Workspace-wide Run/Restore Missing and
copy-and-run actions are intentionally absent.

**Center:** only selected workspace tabs, including all its copies with instance
suffixes. Switching workspaces preserves PTYs, terminal widgets, buffers and
retained scrollback. Last active terminal is remembered per workspace during the
app run. Shortcuts and tab drag-reorder act on the visible workspace only.
An empty workspace has no hidden shell as its active action target.

**Duration:** right-aligned terminal ages like `42s`, `12m`, `2h 04m` measure the
current shell session from successful spawn, not server uptime or command runtime.
Age freezes on exit and resets for a fresh shell. Restarting a server command
inside the same shell does not reset age. Monotonic time avoids wall-clock jumps;
running time is never restored after reopening Ports.

**Startup restores navigation only.** No previous shells or saved commands run
automatically, and there is no automatic shell-restore prompt. Old saved session
definitions remain retained for migration/recovery, not execution.

## Ports inspector and actions

**Right:** collapsible ports inspector (header toggle or Ctrl+Shift+E). Managed
listeners default to the selected workspace; switch to All workspaces to inspect
all live session ports. External is machine-wide, noise-filtered, independently
collapsible, and uses the same row controls. The inspector auto-hides at narrow
widths without changing stored user preference. Left workspace names remain visible.

Click a managed owner heading to jump to its workspace and tab (Other terminals
if unpinned). Click port to open loopback HTTP URL; right-click for Copy URL,
label, optional HTTP checks and process termination. Exact port search is global,
bypassing display filters and workspace scope. Labels are persistently scoped.

Open/Kill controls are parented to fixed in-row slots and keyboard reachable.
Earlier floating-hover artifact was these unparented controls becoming separate
native windows, not a tooltip. This remains covered by hover-window tests.

Header uses circular-arrow Restart, stop-square Interrupt, red octagon-× Kill,
and broom Clear with explanatory tooltips. Clear removes scrollback without
stopping the process. Restart uses a saved explicit command and supported shell
readiness; never blind Up+Enter. CMD requires explicit prompt-ready confirmation.

### Shortcuts

- Ctrl+Shift+T: new terminal in selected workspace
- Ctrl+Tab / Ctrl+Shift+Tab: next/previous visible terminal
- Ctrl+1…9: visible terminal by position
- Ctrl+W / middle-click tab: close selected terminal with safeguards
- Ctrl+F: floating buffer search; Enter next, Shift+Enter previous, Escape closes
- Ctrl+K: command palette (Load workspace, New terminal, Find port, Preferences)
- Ctrl+Shift+E: toggle ports inspector
- Ctrl+= / Ctrl+-: terminal font size
- Ctrl+/: shortcut sheet

Preferences includes General, Appearance, Ports, Recovery and About, validation,
font size, copy-on-select, motion, inspector visibility, filters and probe interval.
No left-icon-collapse or auto-shell-restore settings remain.

## Persistence and safety

`%APPDATA%/Ports/config.json` uses atomic replacement. Existing profiles, labels,
recovery behavior and saved definitions migrate without deletion. The first update
loads existing profiles into navigation once; afterward an explicitly empty list
stays empty across restarts. Missing profile IDs are pruned with a notice; malformed
or newer config remains read-only until explicit backed-up recovery.

Windows job assignment precedes user shells through a bootstrap event; fallback
attribution warnings are visible if unsupported. Windows termination is forceful;
PID/start identity and selected socket ownership are revalidated, with session
roots and critical targets protected. Watchers may respawn terminated listeners.
WSL validates Linux identity/socket ownership before signals; never kills a distro
or Windows forwarding process to free a guest port. Inaccessible ownership stays
unknown. WSL detached/disowned cleanup is not guaranteed.

Polling and actions run outside GUI thread. Failures mark stale data, not empty
success. HTTP checks are opt-in with bounded workers/deadlines and describe
response/refused/timeout/protocol mismatch, not guaranteed service health.
Terminal streaming is raw-byte-accounted and bounded at 1 MiB; scrollback defaults
to 10,000 lines. Bash hooks are normalized for Windows CRLF editors at launch.
Prompt markers are metadata, not cryptographic protection against same-user code.
Avoid secrets in saved commands; JSON is not a credential store.

## Design and licenses

Neutral gray native Qt interface, supplied SVG/ICO product mark, consistent line
icons, Segoe UI and Cascadia Mono/Consolas. No new UI runtime dependencies, CDN
assets, or terminal-output animations. Reduced motion is respected. PyQt6 is
GPL/commercial; see THIRD_PARTY_NOTICES.md before distribution.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe tools/workspace_check.py
.\.venv\Scripts\python.exe tools/workspace_check.py --width 1024 --scale 1.5 --wsl
.\.venv\Scripts\python.exe tools/struct_check.py
.\.venv\Scripts\python.exe tools/hover_probe.py
.\.venv\Scripts\python.exe tools/e2e_check.py
```

Tests cover navigation migration, empty remembered lists, unpin/reload, instance
identity, subset reorder, active selection, inspector scope, fake-clock age and
real shell age, existing process controls and streaming. Real desktop check verifies
Windows CMD/PowerShell and Ubuntu Bash command output, stable PID/view/buffer across
scope switches, age, and app reopen with zero restored sessions. Checks isolate
configuration and control only their own test processes. WSL tests require Ubuntu
and report prerequisite/coverage limitations honestly.

Native GPU/context warnings still occur on this host; renderer output checks pass,
but screenshot fidelity, taskbar/IME/screen-reader checks need interactive hardware
validation. Passing tests does not guarantee zero bugs. No independent-review service
was available in this session.
