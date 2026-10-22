# Workspace navigation design — 2026-10-21

Approved plan: Workspace Tree and Tabs. Preserve prior plans and uncommitted code.

Left: always expanded, resizable workspace tree, minimum 220px. Load remembers definitions without spawning. Remove unpins only; live sessions move to Other terminals and reconnect on reload. Groups may collapse, sidebar never becomes an icon strip.

Center: only selected scope's tabs, all workspace copies, last-active selection per scope, persistent global session/view objects. Reorder and shortcuts act on visible subset. All Start actions target one terminal after executable-content review.

Right: collapsible ports inspector, selected/all managed scope and global External group; exact search remains global. No duplicate terminal panel.

Session durations use monotonic timestamps after successful PTY spawn, freeze on exit, reset on new shell, never persist running uptime. One UI timer updates duration cells only.

Migration remembers existing profiles once; explicit empty remembered list survives subsequent starts. Startup restores navigation only; never shells/commands. Neutral gray reference hierarchy, compact rows, fixed-width durations, reserved accessible action slots. No new dependencies.

Execution ledger: navigation and fake-clock tests written first and failed on missing module. No push/merge/commit authorized. Compatibility: obsolete settings remain accepted but no longer control left collapse or automatic session restoration. Runtime selection IDs are not persisted across process restarts.

Verification: 92 tests passed; compilation and pip dependency check passed. Real workspace_check passed at 1280 (Windows CMD/PowerShell) and 1024/150% with Ubuntu Bash, with actual command output, retained PID/view/buffer, elapsed ages, unpin/reload and reopen yielding two loaded profiles and zero sessions. Structural assertions passed for expanded 260px left tree, zero launched shells on Load, right ports inspector and no bulk Run. Hover assertions passed for no extra native windows, contained controls and stable port geometry. WSL qualification exposed CRLF hook and quoted positional argument issues; startup now normalizes a private per-session hook. Screenshots captured; Qt GPU/context diagnostics prevent full visual/hardware accessibility sign-off. No independent review tool available. Original approved plans unchanged.
