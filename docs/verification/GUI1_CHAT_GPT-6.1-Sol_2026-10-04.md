# GUI-1b initial connected Chat verification

Contributor: **GPT-6.1 Sol**. Checkpoint: **2026-10-04 00:44:08 +01:00** (Europe/London). Status: **in progress**, not stage complete. GUI-1a/GUI-0b gates remain open.

## Implemented source

- `clients/desktop_shell/ChatPresentation.cs`: inert speaker/timestamp/text/code projection, exact append detection and modifier/IME submission predicate.
- `clients/desktop_shell/ChatControls.cs`: native read-only transcript, append/no-change rendering, bounded selection/native-scroll retention, new-message signal and composition-aware composer.
- `clients/desktop_shell/ShellSession.cs`: metadata-only selected-file snapshots/IDs, typed `file_paths`, three-file limit, case-insensitive duplicates and draft revision retention. Success clears only submitted selections/revision; failure/Stop retain intent without replay.
- `clients/desktop_shell/ShellForm.cs`: native picker and path entry, removable filename chips, More menu, hosted Chat without prototype graph tabs, shared compact/expanded layout and explicit New messages.
- `clients/csharp_tests/{csharp_tests.csproj,ShellPrototypeTests.cs}`: linked pure presenter and twelve additional test instances. This is not a native control automation suite.
- `scripts/verify-gui-shell.py`: deterministic rendering reply for exact prompt `GUI1 transcript fixture`. Existing fixture behavior preserved; no production response substituted.

No canonical setting/schema/store changed. Core AppSettings remains v9; UI preferences remain version1. Ordinary Desktop launch remains the default. Settings in Shell remains read-only; no activity chips or voice parity is claimed.

Final source SHA-256:

| File | SHA-256 |
|---|---|
| ChatPresentation.cs | `A0C629B09499DD3DDA6D27B7AAF2F7409C5D9DDA5E308CDDE49AA3D2E606BA6C` |
| ChatControls.cs | `F3AC384C937DAE4F752650F8331EF3B38340AAF5E9948B11ED92CCE87852C03C` |
| ShellSession.cs | `2AA5CB0DBBD75A011F3C97A52B54AA31931832B2ADC9A5CCBE16CAE3215614FF` |
| ShellForm.cs | `F36A4AF3C23CEC76DE0D8EA83711B17A6DFD49206525A5C9E4F3EBB948740A9C` |

## Fresh automated checks

Verification used Windows, .NET10 and Python3.12.10 in isolated `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003`, not the owner's live `.venv`.

| Command | Result |
|---|---|
| `./scripts/verify.ps1` in the isolated environment | **703 Python passed, 25 opt-in skipped, 102.59s**; **8 PWA passed**; ruff, mypy **262 files**, exported-schema check and compileall passed; exit0 |
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **123 passed, zero failed/skipped**, final rerun after native tests; exit0 |
| `dotnet build clients/desktop_shell/desktop_shell.csproj --verbosity quiet` | zero warnings/errors; exit0 |
| `dotnet build clients/desktop_app/desktop_app.csproj --verbosity quiet` | zero warnings/errors; exit0 |
| `dotnet build clients/desktop_widget/desktop_widget.csproj --verbosity quiet` | zero warnings/errors; exit0 |

Added presenter coverage: typed paths without inline contents/previews, duplicate/limit/malformed selection, immutable selection snapshots, success/failure/Stop retention, exact cancel nonce, newly re-selected same path/new draft retention, edited-then-restored draft revision, inert code/HTML/URL/Unicode projection, changed/deleted message detection and seven keyboard/IME predicate cases.

The existing skipped native/model/avatar/voice probes are still skipped. Passing fixtures do not establish provider availability, real inference or physical hardware acceptance.

## Actual native user-side observations

Used the **Computer Use skill** and its supported Windows APIs. Visible native Chat was attached only to dedicated fixture Core at loopback port18793/profile `.local/gui1-chat-native-20261004`. Host PID12368 began00:34:32. Providers were deterministic; all eight local companion capabilities and window/desktop context were disabled. No real model, helper, avatar, microphone or owner profile was used.

| Native action/observation | Result and boundary |
|---|---|
| Enter `GUI1 transcript fixture` via accessibility value-setting, click Send | Canonical deterministic response rendered; successful original draft cleared. Not physical typing or real inference. |
| Inspect top of long transcript using native document/Control+Home | Visible speaker/time labels, code in monospace, `Ω`, full inert URL and literal `<script>neverExecute()</script>`. No HTML execution or URL navigation. |
| Click Attach; set synthetic file path in native picker; accept Open with Alt+O | Filename chip appears. The helper's element click on Open failed because the modal extended beyond parent-window bounds; keyboard shortcut worked. Only synthetic `.local/gui1-chat-selection-20261004.txt` selected. |
| Send selected file with file reading statically disabled | Truthful error `Local file reading is disabled in Settings.`; draft and chip retained; no per-file permission prompt or automatic retry. This is denial-path evidence, **not successful native file reading**. |
| Toggle Compact | Same draft, chip and canonical transcript retained in compact layout. Final reference-style visual/DPI acceptance not claimed. |
| Click selected-file chip | Selection removed; `Test-Path` confirmed synthetic file still exists. No file deletion performed. |
| Send a normal fixture turn while transcript is scrolled to top | Canonical user/reply appended without jumping to bottom; scrollbar stayed at0; New messages appeared. This turn had no attachment after explicit removal. |
| Click New messages | View moved visibly to latest user/reply; affordance hidden. Accessibility tree immediately after input sometimes lagged screenshot, so later refresh confirmed state. |
| Send `GUI0 slow response`, then native Stop | Waiting state and enabled Stop observed; cancellation settled with `Response stopped. Draft retained; dispatched effects are not undone.` and original draft retained. |
| Close Chat, reopen through same-profile `--show chat` IPC | Host remained alive; compact Chat, transcript and stopped-turn draft returned. No automatic resend. |

The helper repeatedly reported the transcript as focused even when screenshot/selected text suggested the composer. No blind typing was attempted. Accessibility value-setting proved form binding/Send, **not physical Enter/Shift+Enter/IME behavior**. An attempted injected wheel scroll did not move the transcript; Control+Home and New messages did. Do not count that wheel attempt as passing mouse-scroll acceptance.

## Cleanup and preservation

Attached-only host Quit was requested through same-profile `--show quit`. Host PID12368 subsequently absent. The fixture's own STOP sentinel was added and original fixture exec session38157 finished normally with exit0; port18793 no longer listening. No force kill was used. The synthetic file and isolated QA artifacts are retained locally, not owner data.

Owner Core **PID52000**, start **2026-09-29T21:49:32.7934609+01:00**, remained unchanged after cleanup. The owner Core was not restarted or reconfigured. `git diff -- SORA_OVERVIEW.md` empty. All five approved reference files matched their manifest sizes and SHA-256 hashes. Dirty/concurrent model work and previous logs preserved.

## Remaining gates / next work

- Positive native selected-file reading and provider context/result acceptance; broader image/missing/deleted/inaccessible-file errors. This fixture deliberately did not enable file reading.
- Physical Enter/Shift+Enter/IME, keyboard traversal, native selection/copy retention over refresh/restyle, screen-reader/high-contrast/OS text scaling and mixed-monitor/fullscreen/sleep acceptance.
- Exact canonical message-ID selection/viewport anchoring when bounded history pages shift; paging/browser UI. Current replacement path retains only bounded character positions/native scroll.
- Full supported activity/evidence chips and retained task/board/content/project/integration workflows (GUI-1c), actual shared voice integration (GUI-1d), complete Settings (GUI-2), canonical Memory/panel semantics (GUI-3), scheduler (GUI-4), final reference styling/graph (GUI-5) and ordinary default/release (GUI-6).
- GUI-1a immediate pre-API cancellation/host-loss startup registration and broader failure/physical acceptance. Initial Chat progress does not waive these or GUI-0b review.

No additional stage-completion date is assigned. The roadmap's three GUI-0 scope completion timestamps remain unchanged.
