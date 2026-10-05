# GUI-1a attached-profile host foundation — GPT-6.1 Sol

Checkpoint: **2026-10-03 20:00:01 +01:00** (Europe/London). Status: **in progress**. This delivers the attached-profile windowless host foundation, not the full GUI-1 stage or final reference-style Chat. GUI-0b's remaining accessibility/DPI review is not waived.

## Implemented

`clients/desktop_shell` now supports an explicit `--state-root` host mode. A windowless `ApplicationContext` owns one tray, a Ctrl+Alt+Space registration, one connection/refresh coordinator, shared Chat session/draft, independent recovery Settings and a transient command menu. Closing Chat hides it, including while a response is pending; closing panels is not Stop response, Cancel task or Quit. Without `--state-root`, the earlier GUI-0 prototype remains available, including its labelled synthetic graph tab. The production host does not show that fixture graph as real Memory.

Profile identity uses the full normalised state-root path and current Windows user SID in a versioned digest. Reparse-point/junction aliases are rejected instead of silently creating a second profile identity. The profile mutex is held by the primary UI thread. Repeated launches use bounded length-framed, current-user-only named-pipe commands; they do not start Core/model/voice/player services or a second state owner. A secondary `--show menu` launch is only a transient command sender, not another connection coordinator/Core. Payloads are capped at 2048 bytes and command/identity enums are validated. IPC timeouts/errors do not trigger duplicate startup.

New owner-local authenticated `GET /api/v1/runtime/identity` exports the versioned `runtime-identity` contract: Core instance UUID, resolved state root, owner/project IDs. No token is returned. Remote callers are forbidden. Hosted `ShellSession` verifies this identity before reading Chat/Settings or enabling effects. An optional `X-SORA-Core-Instance` header rejects requests addressed to an old instance with `409 RUNTIME_CHANGED` before dispatch. The existing transport supports this binding without changing unbound legacy clients. New-instance reconnect resets the event/message projection and does not replay effects; token contents remain in memory only.

The command menu opens Chat, Settings/recovery or explicitly quits the desktop host while leaving its attached Core/tasks running. It works without inference/avatar. Shortcut registration failure leaves menu access available and is surfaced in tray status. Shortcut configuration, avatar menu routing and complete microphone status are not delivered yet.

## Actual Windows checks

Computer Use operated only the isolated QA profile `.local/gui1-host-core-20261003`, port 18798, with deterministic dialogue and all eight local effect switches disabled. The owner Core PID 52000 remained untouched. The fixture is **not real LLM, native desktop-action, agent or physical voice acceptance**.

| Check | Observed result / boundary |
|---|---|
| Windowless boot | Primary host PID 31256 launched with `--show none`; no SORA frame opened |
| Repeated launch / one owner | `--show chat` exited the secondary process; only primary 31256 remained as the host and one Chat window opened |
| Draft / hide / reopen | Entered `GUI1 draft retained when Chat is hidden.`; standard close hid Chat; the same host remained alive and reopening retained the draft |
| Actual GUI Stop | Sent exact `GUI0 slow response`, observed Thinking/Stop, pressed Stop; UI reported response stopped, draft retained and no undone-effects claim; settled back to ready |
| Cancelled transcript | Authenticated canonical message query was empty after the cancelled fixture turn; no generated assistant reply was invented |
| Independent Settings | With Chat hidden, repeat launch opened the read-only 84-field recovery projection through the existing host |
| Recovery command menu | Native transient menu rendered with Chat/Settings/Quit controls and explicit attached-Core boundary at 144 DPI / 150% |
| Found DPI issue | Initial menu used physical dimensions, clipping long Quit/status text. Fixed logical scaling and shorter label; final native render was readable without scrolling |
| Found shutdown defect | First Quit exposed `The CancellationTokenSource has been disposed.`; double cleanup of host/panel resources was made idempotent, not counted as a passing shutdown |
| Final-source shutdown replay | Primary final-source host PID 55436 opened Chat, hid it, and quit through final-source native menu. Afterwards **zero SoraShell processes**, no error window, and the attached fixture Core still authenticated/reachable |
| Fixture cleanup | Only after successful attached-host Quit was the separately owned fixture stopped via its STOP sentinel; exit 0. No listeners remained on 18795–18798, no QA shell remained, owner Core 52000 still alive with its original start time |

The UI checks included an intermediate binary for initial single-instance/draft/Stop flows and a final binary for shutdown replay. Screenshots were inspected in tool output, not saved as evidence assets. An immediate window inventory can precede WinForms close/start processing; final fresh captures/process checks were used for conclusions. A native button geometry failure was recovered through a fresh screenshot-backed observation and one coordinate retry. A terminal attempt at combined Quit verification was rejected by tool policy and not executed; shutdown was ultimately tested through the native command menu.

## Fresh verification

- `./scripts/verify.ps1` in `.local/frontend-verify-20261003`: Ruff passed; mypy **259 files** passed; schemas current after contract export; **686 Python passed / 25 opt-in skipped** in 89.33 seconds; compileall passed; **8 PWA tests passed**; exit 0.
- `dotnet test clients/csharp_tests/csharp_tests.csproj`: **57 passed** after the final cache-only refinement. Four added host tests cover explicit profile/options/identity, bounded current-user IPC/mutex dispatch, wrong-profile rejection before reads/effects and epoch-change resync while preserving marked stale transcript/draft. Existing 53 tests remain green.
- Shell, desktop app and widget builds passed with **zero warnings / errors** after the shared transport change; final shell rebuild after menu/disposal changes also passed with zero warnings/errors.
- The new API test verifies authenticated identity, remote denial, different epochs, matching instance acceptance and stale-instance rejection before message writes. An initial fixture constructor used the wrong keyword (`target` instead of `path`); corrected against the actual protocol constructor. Ruff formatting errors were corrected before the final full gate.
- A rebuild while the shutdown-error dialog still held the old executable encountered copy-lock failures. The inspected dialog was dismissed normally, cleanup was corrected and the final rebuild passed. No force kill/reset was used.

Unity and physical/hardware/provider suites were not rerun, because no Unity or provider implementation changed. The 25 skipped opt-in tests remain unresolved, not implied passes. Original reference files and source overview are preserved.

## Current entry point and remaining delivery

This is **opt-in developer host mode**, not a replacement for `Start-SORA.ps1` yet. Example against a deliberately selected compatible Core/profile (replace paths with that profile; never use the QA example to overwrite owner state):

```powershell
& .\clients\desktop_shell\bin\Debug\net10.0-windows\SoraShell.exe `
  --core-url http://127.0.0.1:8765 `
  --token-file C:\path\to\profile\private\sora-api-token `
  --state-root C:\path\to\profile `
  --show menu
```

`--show none` gives windowless host boot; `chat`, `settings` and `menu` are model-independent entry requests. This binary does not start a missing Core. A long-running older Core without the new identity endpoint will fail closed with recovery diagnostics; it was not restarted automatically during this work.

### Final reconnect refinement — 2026-10-03T20:07:40.0438055+01:00

After the successful native shutdown replay, source review found that replacing the sync presenter on epoch change could discard the last-known transcript if the subsequent projection read failed. `WidgetSync.ResetForNewCore` now resets cursor/readiness but retains cached messages as stale until a successful canonical resync. A dedicated new fixture test proves cursor zero, disabled Send, preserved transcript/draft, new identity binding, recovery and no replayed effects. Final C# count **57 passed**, all three final Windows builds **zero warnings/errors**. This refinement changed only the reconnect presenter/transport, not the already-tested shutdown/menu implementation; its epoch race evidence is component-level, not an additional actual restart/GUI test.

Still required for GUI-1a: managed launch/identity discovery/readiness and graceful owned-service shutdown; helper-preserving launcher integration; versioned UI preference import/placement/reset; configurable shortcut; broader DPI/fullscreen/sleep/focus acceptance. Still required for GUI-1b/c/d: approved transcript/composer design, attachments/scroll/IME, retained task/board/content/agent/path surfaces and actual voice integration/closed-panel microphone indication. Settings here is read-only feasibility/recovery, not GUI-2's full editor. Real Memory/Automation/presentation services and the four-panel visual completion remain later roadmap stages.
