# GUI-1d shared Voice controls — verification

Model name: **GPT-6.1 Sol**. Implementation/verification checkpoint: **2026-10-04 03:11:17 +01:00**, Europe/London. Status: **implemented slice / GUI-1d in progress**. No full-stage completion time.

## Implementation and authority

ShellHost opts the one ShellSession refresh loop into GET voice/local, regardless of panel visibility. The new VoicePanel owns native controls/transient hold intent only; no timer, PCM, model, speech worker or settings database. Profile commands/IPC/tray/menu/Chat More/root/full launcher expose voice; logical placement is UI preferencev1's11th supported key. Opening/hiding does not Start/Close the audio worker. Settings remains canonical v9 and the categorized editor/device selection remains GUI-2.

Explicit Start/Begin/End/Stop/stop_output/Close use a closed vocabulary and existing authenticated route. Each action has fresh state/policy checks, mutation/pending-work flags, async generation fencing and Core epoch verification. A held episode cannot release/stop a new Core. Task/settings mutation is blocked during pending audio control; explicit cleanup controls are distinct from new Begin/Start. Unknown acknowledgement is not replayed. Pending actions make microphone state unconfirmed, not falsely Closed. The host refuses Quit while a hold or audio command is pending.

PressToTalk retains release/discard intent while Begin is pending; success sends one retained End/Stop, uncertain Begin plus explicit release tries a safety Stop without repeating Begin. Mouse/Space release sends speech; actual focus/capture loss and hide request discard. Normal mouse-up capture release is distinguished from capture loss while the left button remains down. Mouse/key physical timing is unverified. KeyDown no longer uses SuppressKeyPress, which can suppress KeyUp: separate Handled/KeyPress handling is implemented in new and compatibility voice surfaces, following [Microsoft keyboard-event documentation](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/input-keyboard/events). This is a source correction, not proof of real hardware key release.

The existing audio worker publishes nullable microphone_open independently of general state; capture close is attempted even if abort fails. Bridge invalidation marks an unconfirmed live shutdown Unknown until the reader drains; process completion clears the report. Tray always uses current worker metadata or explicit Unknown/stale labels. Older Core responses with no microphone field never imply Closed. The icon is a source-level recording/unknown/closed indication, not a measured OS privacy icon/device probe. Voice state and dialogue-model readiness are shown separately.

Actual bounded128-device inventory retains key/channels/optional adapter index. Duplicate keys are labelled ambiguous, not deduplicated into a false selection or allowed to erase microphone status. Editing keys/paths/voice/speed/recording duration remains in the upcoming canonical Settings editor. No adapter/device was enumerated live during these tests.

Added stop_output through owner-local static-policy route/bridge/worker, calling existing stop_speaking(cancel_generation=False), without stopping capture, resetting generation/frames or cancelling the response task. Existing full Stop discards capture/cancels the voice response; Close closes local audio explicitly. PCM/private diagnostics remain outside GUI/Core HTTP. Remote scopes still cannot use local audio. No per-use permission request or second speech worker.

## Fresh checks

| Check | Result |
|---|---|
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **231 passed**, zero failed/skipped, final tests warning-free |
| `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` | **710 Python passed /25 opt-in skipped in86.13s**, **8 PWA passed**, mypy267/lint/schema/compile; exec59396 final exit0 |
| Shell/Desktop/Widget final builds | zero warnings/errors after keyboard/pending-status refinements |
| `./scripts/verify-shell-launchers.ps1` | effect-free real-full-launcher AST defaults/explicit/retained panels includingVoice/unsupported effort passed |
| `git diff --check` | exit0; existing LF→CRLF warnings only; explicit read-back/tests cover untracked source |

**21 new C# cases (210→231)** cover opt-in shared read/no audio Start, model-down independent status, explicit nullable capture/old-Core unknown/stale/error behavior, six exact action bodies, static-off Begin refusal/Close allowance, epoch preflight/reply/release refusal, pending mutation exclusion and no replay, begin/release/loss/failure races, synchronous failure clearing hold, panel/placement command compatibility and honest ambiguous devices. UI forms/native event dispatch/tray icons are build-verified, not directly executed by the non-Windows component suite.

**Four new Python tests** cover output-only worker action preserving capture/frames/generation/response task, abort failure still closing capture/reporting metadata, microphone flag independent of general worker state and false after mock process exit, and actual isolated HTTP status/stop_output/static-off/invalid-action/Close/remote isolation with mocked audio command. Focused voice tests also passed14/4 opt-in skipped. No real audio process, microphone, speaker, model, actual spoken prompt, agent or mouth relay was used.

Intermediate lint/typing errors in the new fixture and an xUnit filtering warning were corrected before final verification. Full Python/PWA finished before later C#-only pending-status/keyboard/model-label refinements; final231 component tests and all three final product builds cover those sources. No Python/API/schema change followed the successful full run.

## Acceptance still required

**Preservation/read-back checkpoint: 2026-10-04 03:14:31 +01:00.** All103 local links in the four updated/new documents resolve; all9 original reference/draft/overview byte sizes/SHA-256 hashes match the prior baseline. Exactly3 original completion checkboxes and their19:24:55 timestamps remain. These are preservation checks, not a new stage completion or native proof.

Native mouse/Space autorepeat/release/capture/focus/hide, microphone indicator with panels closed, pending Quit/explicit worker Close and high-contrast/DPI/screen-reader behavior. Full human-spoken speech→LLM→output→mouth flow, barge-in versus output-only stop, device loss/recovery and real configured model are still open. Worker recording limit is2–60seconds; network failures may prevent timely closure confirmation. Do not promise immediate physical capture closure, successful delivery or absence of audio solely from the UI ACK/state. Core-identity-refresh/action races and real transport latency need native acceptance as well.

Earlier policy-rejected GUI setup was not retried via another path. No native computer-use action occurred this turn. Owner Core PID52000/start2026-09-29 21:49:32 local stayed `.venv\Scripts\sora.exe`; no owner microphone start, restart, settings/data write, `.venv` replacement, paid probe, force kill, reset or commit. Isolated HTTP fixture servers/runtimes close in finally blocks. Compatibility forms/default Desktop remain available. Original stage completion history/model attribution/reference originals are preserved.

Next implementation is GUI-2 full canonical Settings, preserving all previous native/physical acceptance gates and GUI-3–GUI-6 scope. [Roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Runbook](../runbooks/SORA_DESKTOP_SHELL.md) · [Progress changelog](../../changelog/2026-10-04T031117+0100_GUI1d-VOICE-PROGRESS_GPT-6.1-Sol.md).
