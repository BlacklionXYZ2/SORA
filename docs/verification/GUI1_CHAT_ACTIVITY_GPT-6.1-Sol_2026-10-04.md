# GUI-1b anchors/file context and GUI-1c initial Activity

Contributor/model: **GPT-6.1 Sol**. Checkpoint **2026-10-04 01:03:57 +01:00** (Europe/London). Both stages **in progress**, not complete. Previous [initial Chat evidence](GUI1_CHAT_GPT-6.1-Sol_2026-10-04.md) remains historical, not relabelled final-source native proof.

## Changes implemented

`ChatDocument.cs` maps measured native text spans to canonical message IDs. Selection boundaries survive unchanged messages moving after bounded history shifts/prepends; ending exactly at a message boundary does not select a new appended message. Deleted/corrected/missing-middle/reordered/duplicate/blank-ID selections fail restoration instead of selecting unrelated text. Viewport fallback chooses a surviving old message, then the first current message. `ChatControls.cs` uses the map during replacement/restyle; append still restores native scroll and no-change refresh still avoids rebuilding. This is a UI cache, not canonical persistence or a history browser.

`ActivityForm.cs` is a summonable native secondary window on the existing shared session. There is no panel timer/full-state poller/connection/store. It shows bounded canonical task IDs/status/backend/result references; explicit evidence reads show original owner request versus SORA suggested brief, model/effort/project/mode/base ref, provider-reported results/artifacts and coverage. HTML/paths/URLs remain inert read-only text. No final result is labelled as such. Selection/read revisions prevent late evidence from switching targets; instruction revisions prevent a successful older steer from clearing newly edited text. Closing hides the panel; actual host shutdown closes/disposes it idempotently.

`ShellSession.cs` adds model-independent `CanUseCore`, exact-ID/epoch-checked evidence reads and serialized task controls. Before Cancel/Steer, it re-reads the captured task ID/current state and rechecks connection/host/epoch. Known active states only; planned/terminal/cancel-requested/interrupted/unknown targets rejected. Acknowledgement ID/epoch checked. No automatic retry or Chat-request reuse. Host native/IPC/delayed Quit refuses pending task control. Cancellation is not Undo or independent proof of every effect.

Activity entry is wired through tray, command menu, Chat More, bounded same-profile IPC/direct `--show activity`, root/full launchers' `-ShellPanel activity`, and profile UI placement. UI preferences remain version1; max recognized panel keys rises4→5 with Activity. Old files still load; an older binary reading the new key fails read-only rather than overwriting it. Canonical AppSettings remains v9. No public Core contract/migration or ordinary default switch.

The isolated fixture script adds optional `--file-fixture`: requires a fresh repository `.local` profile, creates one synthetic text file and enables file read in that QA profile, with other desktop/helper/voice/delegation/write capabilities disabled. Default behavior still disables file reads. Exact prompt `GUI1 attachment fixture` verifies both the owner-selected-data label and synthetic marker in the provider context; it reports NOT observed when absent. A Python regression verifies it cannot blindly claim success from only a marker without the selected-file context label.

## Fresh automated verification

| Check | Result |
|---|---|
| `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` | **704 Python passed, 25 opt-in skipped,85.77s; 8 PWA passed**; lint/mypy **263 files**/schema check/compileall passed; exit0 |
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **148 passed, zero failures/skips**; exit0 |
| Shell/Desktop/Widget `dotnet build ... --verbosity quiet` | each zero warnings/errors; exit0 |
| `./scripts/verify-shell-launchers.ps1` | defaults/exact selections/Activity/unsupported effort passed; effect-free forwarding fixture only |
| PowerShell parser for root/full launchers | both ASTs passed |
| `git diff --check` | no whitespace-error diagnostics; existing LF→CRLF warnings only; this does not verify untracked files |

Added **10 C# anchor cases** plus **15 Activity cases** (123→148): shifted/prepended history, boundary, native line endings/Unicode, removal/correction/cross-message reorder/ambiguity/fallback; model-down task control independent of Chat; seven terminal/unknown states; ID/offline/host refusal; concurrency and epoch change before mutation; acknowledgement mismatch/no replay; old-epoch acknowledgement; invalid target/action/instruction; inert owner/brief/provider evidence; bounded Activity CLI/IPC/UI placement.

An initial script-only mypy command could not resolve typed source packages; the subsequent source-inclusive and full prescribed commands passed. Initial fixture help text exceeded lint line length and was repaired before final gates. No failed command is counted as a pass.

## Actual fixture/API and native evidence

Fresh Core `.local/gui1-chat-file-anchor-20261004`, port18792, used deterministic providers and only synthetic data. It was not a live LLM/agent run and incurred no model probe. Native attach-only host PID29856 started00:52:26. Computer Use listed/captured actual empty connected Chat, but clicking More failed with **`failed to activate captured window`**. After fresh window recovery, the one retry failed identically. GUI inputs stopped per skill; no blind keyboard/typing or alternate UI automation was used.

The positive path was then verified by authenticated **actual HTTP dialogue**, with typed `file_paths` pointing only to the generated synthetic file and a unique request ID. Response:

> GUI-1 deterministic attachment fixture: selected-file marker observed in provider context. No real LLM inference.

The fixture verifies the marker in the provider's supplied context, not echoing the prompt. GET canonical messages confirmed the source marker absent from message content. This proves Core file-context delivery for that fixture, **not native picker/Send operation on the new binary, real model understanding, image handling or all-store retention policy**. The earlier native disabled-file/picker checks remain the preceding checkpoint's evidence.

After final source/builds, attach-only host PID28344 started01:02:39 with `--show activity` while the fixture Core was offline. Read-only Computer Use capture (no activation/input) showed **SORA · Activity and task evidence**, readable task/status/agent/result headers, empty canonical list, inert evidence area/instruction box, explicit offline/stale status and disabled evidence/Cancel/Steer controls. This is actual final-source offline rendering—not selection, successful task controls, close/reopen or accessibility/online acceptance.

Both QA hosts were Quit through same-profile IPC, and the fixture's STOP sentinel ended original exec session52687 normally with exit0. At01:03:57 both host PIDs absent and port18792 absent. Owner Core **PID52000**, start **2026-09-29T21:49:32.7934609+01:00**, unchanged. No force kill, owner restart/configuration edit or private-file read. QA synthetic artifacts retained under ignored `.local`.

## Final source fingerprints

| File | SHA-256 |
|---|---|
| ChatDocument.cs | `F1EC224741165A94D9634A9F53AE0ABF6CFA54E77486101D1AED012C49F468AF` |
| ChatControls.cs | `150AEBF1F3FA828EF49EC9C62249C0FA92376200E78CF06571DD9EA555B5708A` |
| ActivityForm.cs | `28A46CF9FEB7CD1B40E4FA47D69A31F46CB062AE7C0EAC09D730769890434E40` |
| TaskPresentation.cs | `442EFFF6B08DDED369ABBE543C948FE6CD96E6A7443704B01F3524CDF3CB02C2` |
| ShellSession.cs | `2AB62A826676F591BCE3423164FBECB20B1CAD65717EE8DD6A620F83B227E09B` |
| ShellHost.cs | `DC1D020B4F319BE691B6235A744BD955BA20269D6C609EF913DA06EBBFB6A797` |

Original overview diff empty; all five approved reference files matched manifest sizes/hashes. Previous contributor records/dirty work preserved; no commits/reset/removal of compatibility clients.

## Remaining work

Positive native file/model/error acceptance; native shifted-history/selection/restyle/wheel, physical Enter/Shift+Enter/IME, screen-reader/high-contrast/text scaling/mixed-monitor/fullscreen/sleep; complete history browsing and actual responding provenance. The skipped real model/native/avatar/voice probes remain skipped.

GUI-1c online real-task selection/evidence/Cancel/Steer acceptance; remaining shared agent/delegation selection, board/content/project/Paths/integrations, complete run-history/artifacts and real public-event chips. Initial Activity is not full legacy parity. GUI-1d voice, GUI-2 Settings, GUI-3 Memory/semantics, GUI-4 scheduler, GUI-5 final graph/style and GUI-6 normal launch/release remain open, as do GUI-1a lifecycle/physical and GUI-0b review gates. No additional completed-stage box or completion time.
