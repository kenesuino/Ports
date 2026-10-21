# Ports profiles and polish execution

Approved plan: `C:/Users/Kenneth/.cursor/plans/ports_profiles_and_polish_72b8adc2.plan.md` (unchanged).

Design: reusable multi-terminal workspace profiles; reviewed executable settings; focus existing workspace on Run; explicit copies; independent failed-item retry; sidebar/top-tab views over persistent terminals; session-colored header; supplied app icon and consistent action icons; brief reduced-motion-aware panel transitions.

Execution ledger
- Branch `feat/workspace-profiles`; original base `144a482`.
- Foundation, streaming, and storage workflows independently scoped; GUI/session integration handled together to keep lifecycle consistent.
- Ruling: prompt integration uses per-session random OSC markers for readiness. Markers are metadata, not authorization; they only enable replay of explicitly reviewed commands, never terminal-supplied arbitrary commands.
- Ruling: shell profiles remain enabled. Unsupported readiness yields explicit confirmation rather than a timer.
- Ruling: no automatic git commits or changes to original approved plan. Real rendering needs actual WebEngine verification separately from mock-based tests.

Verification record
- 55 tests passed on final run, including Windows ConPTY and live Ubuntu WSL listener/signal tests; pip check clean.
- Actual Qt WebEngine bridge and displayed command output passed at desktop 100%, 150%, and 200% configured scales; final 1280/100 and 1024/150 reruns have all three sessions ready and no session errors.
- Native capture inspection was inconclusive on this graphics environment: context diagnostics and unreliable captures mean visual sign-off remains open. App icon source bytes match supplied SVG; ICO includes seven sizes.
- Independent review dispatch unavailable: every attempted Task returned `Cursor user message action has no message_id`; all implementation and final source review performed directly. No independent-review claim.
- Remaining ceilings: WSL detached/disowned cleanup not guaranteed; external WSL scanning requires active session helper; expected-port conflicts not a full launch dependency scheduler; native taskbar/IME/screen-reader and manual hover quality need hardware verification.
- Original approved plan unchanged. Source implementation completed with these explicit verification/support limits; no production-ready claim.
