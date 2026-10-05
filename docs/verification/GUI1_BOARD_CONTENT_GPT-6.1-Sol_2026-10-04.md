# GUI-1c retained Board, Content and Integrations — verification

Model name: **GPT-6.1 Sol**. Implementation/verification checkpoint: **2026-10-04 02:16:41 +01:00**, Europe/London. Status: **implemented slice / GUI-1c in progress**. No whole-stage completion or ordinary default switch.

## Implementation and scope

The existing compatibility KanbanBoardForm is now injected with the shared host projection/API/workflow. Compatibility FullAppSync exposes its existing WidgetSync workflow; Start planned no longer creates a second synchronizer. ShellSession conditionally reads narrow board/content/extensions/capabilities projections on its existing refresh loop, rather than creating another full-state reader, connection, poller or store. Atomic projection replacement and shape/unique-ID validation retain labelled stale cache after failure; model readiness is not required for matching-Core operations.

Board is a small note-board view with a native expand button, three named lanes, coloured/readable assignee/run labels, explicit collapse/Escape and narrow horizontal scrolling. Canonical add/assign/move/remove/start/retry semantics remain separate from run status. Host injection adds hide/dispose/cancellation/pending-work behavior; UI preferences retain board mode plus three new logical placement keys (ten total), without canonical/private record persistence. High-contrast fallback and logical-DPI layout are source implementation, not physically verified rendering.

BoardNoteDraft pins exact intent/assignee/key/Core epoch across uncertain admission and partial assignment. A known task ID prevents recreation during assignment retry; unchanged version0 can be assigned, an already matching assignment can be recognized, other concurrent versions require inspection. Core changes cannot complete an old partially admitted note. Explicit Restore submitted draft helps identical retry; no automatic mutation replay. Remove clears selection only after acknowledgement. Non-idempotent retry with an unknown outcome is blocked for that exact task in this host session; this is process-local protection, not a new durable retry protocol.

RetainedBrowserForm provides registered Content and read-only integration details. Selection uses exact IDs, unchanged lists do not rebuild, path text is inert, navigation re-reads exact registration inside the serialized mutation slot and sends only the typed Core action. Actual failure/unsupported/limitations remain visible; invalid/mismatched success acknowledgements are rejected. Integration enablement/active projection/provider availability are distinct; grant metadata is labelled historical/remote, not local approval authority. No enable/disable/configuration effects are added.

Tray, command menu, Chat More, profile IPC/options and root/full launchers expose board/content/integrations. Pending board/selector/browser work participates in Quit refusal; all hosted forms hide on user close and share existing profile/epoch guards. Default Desktop remains unchanged, hosted full Settings remains read-only and AppSettings remains v9. Compatibility forms remain available.

## Fresh checks

| Command/environment | Result |
|---|---|
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **192 passed**, zero failed/skipped, no build warnings; final run exit0 |
| `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` | **704 Python passed /25 opt-in skipped in85.63s**, **8 PWA passed**, mypy263/lint/schema/compile passed; exec60606 final exit0 |
| Shell/Desktop/Widget `dotnet build ... --verbosity quiet` | all zero warnings/errors after final product source |
| `./scripts/verify-shell-launchers.ps1` | real full-launcher AST forwarding/defaults/exact options/Activity/Agents/Paths/Board/Content/Integrations/unsupported effort passed; effect-free receiver only |
| `git diff --check` | no whitespace errors; existing LF→CRLF warnings only; untracked files require explicit read-back |

**27 new component cases (165→192)** cover opt-in shared projection/model-down reads, stale cache/recovery, body/key/epoch-pinned plan retry without refresh replay, exact board version/ack identity, unknown non-idempotent retry refusal, registered-content revalidation/failure presentation, cross-epoch reply and mutation serialization, offline/host/disposed refusal, all six assignee drafts, three bounded panel commands/placements, fixed effect vocabulary, manual Completed versus planned status, partially admitted cross-Core refusal, malformed/duplicate projection IDs and UI-only mode/placement restart/old-store preservation.

Full Python/PWA ran after initial product changes but before later C#-only refinements. Python/Core/schema sources were not changed afterward. Final product builds and final192 C# tests cover the final source. Component tests do not establish actual user-side interaction or provider understanding.

**Final source confirmed at2026-10-04 02:23:10 +01:00:** all three builds and192 C# checks were rerun after the host's pending-panel Quit routing and recovered-board-mode refinements. Native focus/preference-recovery interaction remains unverified. A fresh explicit listener count on18795 was0.

## Runtime/UI evidence boundary and cleanup

A fresh deterministic fixture Core was started under `.local/gui1-board-content-20261004`, port18795, `--model-unavailable`; exec26395 reported readiness. Default file/desktop/voice/delegation effects were disabled. No GGUF/provider/private file was used. The Computer Use skill and its three runtime/policy references were read, and its documented JS initialization succeeded.

The subsequent combined synthetic board-seeding/host-launch command was **rejected before execution: `blocked by policy`**. It therefore did not create the planned six notes or launch the GUI. No alternate execution path was used to bypass that rejection. There was no native capture/input, live navigation, Add/Assign/Move/Remove/Start/Retry or hide/keyboard/placement demonstration. Do not describe this slice as native accepted or reuse earlier Agents/Paths screenshots as its evidence.

The dedicated STOP sentinel was then added through apply_patch. Fixture exec26395 exited normally0, and a later explicit listener check reported **zero listeners on18795**. Owner Core **PID52000**, start **2026-09-29 21:49:32** local, remained the existing `.venv\Scripts\sora.exe`. No force kill, owner configuration/data mutation, live agent admission, paid probe, commit or reset. Synthetic QA artifacts remain under ignored `.local`; owner `.venv` was not replaced.

## Remaining acceptance and next work

Native compact/expanded/colour/text/high-contrast/mixed-DPI rendering; Add and partial/uncertain outcome recovery; assign/move/remove conflicts, selector admission/retry, exact registered Content navigation/failure, integration inspection, hide/reopen drafts/selections and hidden pending-work Quit. Real configured provider/project boundaries and broader accessibility remain unproven.

GUI-1c full run-history/artifact/public-chip access still needs supported canonical projections and connected UI; earlier host/Chat/GUI-0b native gates remain open. GUI-1d shared voice, GUI-2 full Settings and GUI-3–GUI-6 remain required. No new completion checkbox/time.

[Roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Runbook](../runbooks/SORA_DESKTOP_SHELL.md) · [Progress changelog](../../changelog/2026-10-04T021641+0100_GUI1c-BOARD-CONTENT-PROGRESS_GPT-6.1-Sol.md).
