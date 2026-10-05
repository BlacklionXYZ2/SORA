# User-side system repair and local avatar hookup

Model: GPT-6 Astra
Recorded: 2026-09-28 08:11 +01:00 (Europe/London)
Status: repairs implemented; acceptance in review, not whole-system acceptance or a phase-completion claim.

## Implemented during 2026-09-27 testing

- Connected the packaged Unity/VRM player to normal local startup, with optional `-AvatarPath` and `-NoAvatar`. The bundled asset is Seed-san, not a newly created custom SORA character.
- Added owner-local companion status and pose controls to the full app. Renderer grants are session-scoped, renewed while valid, and revoked on shutdown; explicit desktop actions remain separately authorized. Unity exits when its parent Core disappears.
- Added thinking/waiting presentation based on direct dialogue/background specialist activity.
- Corrected both Windows entry points to STA and made file dialogs owned by their parent forms.
- Separated long model-response deadlines from short polling deadlines, handled polling timeout as disconnection, added regression coverage, and added pending-action feedback/duplicate-submit protection.
- Reused Unity's physical display discovery in the capture helper. The old helper invented MONITOR1/MONITOR2 IDs and assumed 100% DPI, which raced the live avatar's DISPLAY1/DISPLAY6 topology and caused `stale_layout` failures.
- Improved model rejection/timeout/HTTP error messages without exposing private server bodies.
- Forwarded workspace/write-repository/task-timeout options through the single launcher, preserving Deepseek's separately attributed runtime-routing changes.

## Recorded evidence

- 2026-09-27 15:59:49 +01:00: Unity PlayMode run completed, 59 passed, zero failures; packaged build subsequently succeeded.
- 2026-09-27 21:06:45 +01:00: live full-app attachment turn on the configured Gemma E2B returned the correct project, day, and mascot from the synthetic test file.
- 2026-09-27 evening: `scripts/verify.ps1` passed with 365 Python tests, 10 opt-in skips, and 7 PWA tests; C# regression suite passed 34 tests. A later embodiment verification passed 45 tests with 3 opt-in skips. Final rerun after all edits remains pending below.
- The native file picker opened and selected the synthetic file. The new Wave control reached the running Unity companion. This does not certify subjective animation quality or every physical interaction.
- A purple Hermes note was created through the expanded board in isolated QA state; no agent run was started.

## Repair-stage closure — 2026-09-28 08:18:16 +01:00

- Final `scripts/verify.ps1`: 368 Python tests passed, 10 opt-in skips; 7 PWA tests passed. Ruff, mypy, contract export and compileall passed.
- Final full-app build: zero warnings/errors. C# suite rerun: 34 passed.
- Widget file-picker/preview/send/reply passed using the native interface; the real model returned Thursday, completing at 08:14:35. Slow reply exceeded the former client timeout without dropping the request.
- Board note move passed: purple Hermes note appears under COMPLETED while task status remains planned. QA board persistence survived Core restart.
- Idle Core restart verified the old Unity player exits when its parent stops. Fresh Core and Unity started at approximately 08:17:15. Widget reconnected with retained history, full app reopened against the same Core, and saved settings revision 2 remained active with no restart pending.
- Temporary QA Core was stopped; QA files/history remain available. Current normal session is loopback port 18769. No new external specialist task was started.
- Human-readable acceptance report: `docs/verification/SORA_USER_SIDE_REPAIR_GPT-6_2026-09-28.md`. Updated avatar/model guidance in `docs/runbooks/SORA_LOCAL_TRYOUT.md`.

## Open checks and boundary

- LM Studio's saved model overrides explicitly disable `--mmproj`, including on installed models catalogued as vision-capable. Tiny synthetic image requests independently fail with a missing-projector error. No model-weight download or persistent LM Studio override was made. The user has been asked whether to enable the small installed vision E2B model; the current preferred uncensored E2B remains unchanged.
- Positive desktop-vision inference remains blocked on model/projector choice. Board removal/start/retry and fresh every-provider native acceptance remain untested in this pass; final automated verification and cleanup/report completion are done.
- Phone/certificate, microphone/speaker, display hotplug/DPI changes, and subjective avatar interaction remain manual acceptance; earlier model/provider reports are not relabelled as this run's tests.

Evidence directory: `.local/qa-20260927`. Existing project changes and other-model attribution were retained. No source commit was made.
