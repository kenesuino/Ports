# Workspace profiles and visual update design

Approved 2026-10-21. Target: native Windows developer command center for recurring multi-service projects.

## Behavior
Workspace profiles contain ordered terminal definitions with persistent identities, shell/distribution, starting folder, explicit startup/restart commands, expected ports, and accent. Explicit Run reviews executable settings once per revision, then starts independent terminals. Existing workspaces focus rather than duplicate; missing terminals and another copy require explicit actions. Saving definitions does not scrape terminal output/history. Restoring layout never auto-runs commands.

## Presentation
Sidebar cards and top tabs select the same persistent terminal instances; no WebEngine reload or process restart. Profiles, exact-port search and external listeners stay reachable. Obsidian terminal area, subdued blue/session-colored two-row header, Segoe UI controls, monospace terminal/data, consistent Qt-rendered SVG action icons. Supplied 816×816 SVG is packaged unchanged and rendered to Windows ICO. Retain native title-bar controls.

Motion: 120 ms hover tint; 180 ms collapsible external panel; no terminal-output/tab-switch animation. Respect Windows animation preferences and explicit reduced-motion setting. Visible focus, labelled icon actions, semantic status text.

## Correctness
Prompt readiness replaces fixed startup delay; timer timeout cancels instead of replaying. PID/start identity and endpoint are revalidated before destructive actions. Windows job tracking captures session descendants; WSL uses Linux ownership/signals. Worker snapshots deliver queued GUI updates. Terminal streaming acknowledges raw bytes; Unicode boundaries remain intact. Config migration/recovery preserves data and labels.

## Verification
Focused regression tests precede fixes. Full tests include headless logic and real Windows/WSL processes. Real QtWebEngine readiness, displayed output, and screenshot inspection are separate gates at desktop sizes/DPI. No image-generation service is available; use approved brief and supplied asset, with no pixel-perfect-match claim. Remaining unsupported platform cases must be reported explicitly.
