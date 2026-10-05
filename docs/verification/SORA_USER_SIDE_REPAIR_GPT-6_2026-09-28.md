# SORA user-side repair acceptance — 27–28 September 2026

Model: GPT-6. Updated 2026-09-28 08:18:16 +01:00, Europe/London.
Status: implemented repairs with partial live acceptance; not full-system or release sign-off.

## Findings and repairs

| System | Fresh evidence | Outcome |
| --- | --- | --- |
| Full-app file attachment | Opened the native owned picker, selected a synthetic text file, sent a prompt through Chat. On 27 September at 21:06:45 the local Gemma E2B returned Blue Lantern, Thursday, and green fox correctly. | Passed. Both Windows entry points now use STA; dialogs are owned and no longer launched on a detached thread. |
| Widget attachment | On 28 September opened Attach file, selected the same test file, inspected its preview, then sent a launch-day query. Widget visibly returned Thursday. Model server completed at 08:14:35; the client remained connected beyond the old 12-second deadline. | Passed. No private user document was used. |
| Desktop capture with avatar | Look at screen originally failed with `stale_layout`. The capture helper used invented MONITOR IDs and 100% DPI, while Unity reported physical DISPLAY IDs and mixed DPI. Both now compile the same monitor-discovery source. A retry progressed to model inference rather than stale layout. | Capture integration repaired. Actual topology: primary DISPLAY1 3840x2160 at 150%; secondary DISPLAY6 at negative X, 1280x1024 at 100%. |
| Desktop image interpretation | UI request with installed 12B failed. Independent 128x128 synthetic image requests to 12B and small Unsloth E2B returned an explicit missing-projector error. Corresponding saved LM Studio configs suppress `--mmproj`, despite catalog vision markers. | Blocked on model configuration/choice, not claimed working. Asked owner whether to enable the small vision E2B. Saved preferred uncensored E2B was not replaced. |
| 3D companion connection | Normal Core launched packaged Unity; owner-local status reported running, visible, connected. Wave UI command produced waving state. Core and Unity stayed connected overnight. | Hookup verified at process/protocol level; subjective visual quality not signed off. Bundled model is Seed-san, with a custom VRM path option. |
| Avatar lifetime | At 08:15–08:16, stopped idle Core for restart; its Unity process exited without a separate player kill. | Parent-lifetime guard passed. |
| Note board | Opened compact board, expanded three columns, created purple Hermes note in isolated QA state. On 28 September moved it from TODO to COMPLETED through the confirmation dialog; task remained planned. Note persisted through QA Core restart. | Add, agent colour, move, persistence and run-status separation passed. Removal/start/retry were not exercised in this native pass. |
| Settings/reconnect | Earlier native save showed pending revision, then active after restart. Shared history was visible in full app and widget. Reconnection error footer clears after successful sync. | Save/restart path exercised; not all settings categories or four-surface parity. |
| Polling/slow operations | Fixed timeout cancellation handling so it becomes disconnected/retry state; caller-requested cancellation still propagates. Long dialogue deadline is separate from polling deadline. Added pending-action labels/duplicate-submit guards. | C# regressions and live slow reply passed. |

## Automated verification

- `scripts/verify.ps1`, final 28 September run: **368 passed, 10 skipped**; Ruff, mypy, contract export check and compileall succeeded. PWA: **7 passed**.
- `dotnet test clients/csharp_tests/csharp_tests.csproj`: **34 passed**, including new polling-timeout/caller-cancellation regression; repeated after final board edit.
- `scripts/verify-embodiment.ps1`: **45 passed, 3 skipped**, including real C# transport. Packaged native UI interaction fixtures were not enabled by this command.
- Unity PlayMode completed **2026-09-27 15:59:49 +01:00**: **59 passed, zero failures**. Packaging succeeded after parent-lifetime changes. No later Unity source change was made; capture helper links unchanged Unity coordinate/native sources.
- Full desktop app, widget and capture helper built with zero warnings/errors. Full app rebuilt after the last board guard edit.

Logs: `.local/qa-20260927/verify-20260928.log`, `csharp-final.log`,
`embodiment-final.log`, `core-final.log`; Unity XML/build logs under
`.local/p09-unity-evidence`. The QA state and synthetic attachment remain under
`.local/qa-20260927`; they were not deleted. No authentication tokens or image
payloads are included in this report.

## Not established by this pass

- Positive model interpretation of a captured screen, until the projector setting is resolved.
- Microphone, speaker, barge-in, real paired phone/certificate, sleep/resume, physical monitor/DPI changes, or subjective animation/drag feel.
- Fresh successful runs for every external specialist. Deepseek's separate 27 September report records Hermes success and Codex/Antigravity failures; those are not presented as this model's UI evidence. No provider permissions were bypassed and no external agent was launched by the isolated board test.
- Browser/PWA native interaction, content-handler navigation, extension installation, all board operations, or simultaneous rendered four-client parity. Automated coverage is not substituted for those manual checks.
- All roadmap stages complete. Existing manual acceptance checklist remains applicable.

## Operational notes

At the end of the pass, the isolated QA Core was stopped. Normal Core restarted
on loopback port 18769 with a fresh Unity child at approximately 08:17:15.
Widget reconnect and retained history were checked in the native interface;
the full app reopened against the same Core. Saved/active settings revision 2
matched, restart_required was false, and the preferred uncensored E2B model
remained selected. The previous Unity process exited after parent termination.

Use `Start-SORA.ps1` for a fresh normal session and `-AvatarPath` for a custom VRM.
If Core is already running, open another client with `scripts/open-manual-test.ps1`
and its current port instead of starting another Core against the same state.
The full app was tested with loopback Core/model endpoints. Local file reading
remains bounded by parser/size support and the Windows account's access; remote
clients cannot acquire unrestricted owner-local file access through these routes.

The Computer Use skill informed owned-window/fresh-observation tests. Screenshots,
native UI results, mock regressions, provider errors and prior-model evidence are
kept distinct. The already-dirty repository and Deepseek's model/routing changes
were preserved. No source commit, model download, persistent LM Studio override,
or deletion of user history was made.
