# P15.6 compact widget and expanded chat — GPT-6

Completed: **2026-09-23 07:49:07 +01:00 (Europe/London)**.

## Delivered

- A self-contained Windows Forms companion widget starts from the installed
  `bin/sora-widget.ps1` launcher. The launcher resolves the active release,
  private Core token and local widget settings relative to the install profile;
  credentials are never persisted in widget preferences.
- Compact conversation keeps text input, direct-dialogue readiness, specialist
  activity and lightweight notification controls visible. Expanded mode adds
  readable history, activity/task details and local text, image and DOCX/file
  previews. Technical task IDs remain behind an explicit details control;
  private reasoning is not presented.
- Configurable per-monitor anchor, work-area clamping, always-on-top, quiet
  notifications and expanded state persist across restarts and release
  update/rollback. Enter sends, Shift+Enter adds a newline, Ctrl+L focuses the
  composer and Ctrl+E changes view.
- The client authenticates to literal loopback Core only, reads the token file
  on each request, replays event pages and rebuilds canonical
  message/task/provider projections on reconnect. It retains the last visible
  snapshot while Core is offline.
- Attachments have explicit boundaries: small selected UTF-8 text (at most
  8,000 characters) can be embedded when sent; larger text, images, DOCX and
  binary files are local previews/path references only. No image pixels or
  DOCX bytes are silently uploaded to direct dialogue. This is not full
  document ingestion or a specialist artifact viewer.

## Verification on the Windows development machine

| Command or check | Result |
|---|---|
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1` | 346 Python tests passed, 10 explicit opt-in skips; Ruff, strict mypy across 186 source files, schemas, compileall and browser 7/7 passed |
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | 27/27 passed, including widget geometry, two concurrent runs with reconnect, attachment boundaries and loopback-only transport |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1 -ReleaseId sora-p15.6-acceptance-20260923-r4 -ReuseVerifiedUnityBuild` | Self-contained widget and full release built; reused the separately verified Unity player rather than claiming a fresh Unity test |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-release.ps1 -Bundle .local/releases/sora-p15.6-acceptance-20260923-r4 -RequireWidget` | Passed clean install, update, rollback, data-retaining uninstall and reinstall, with widget executable/launcher checks and settings preservation; machine record: `.local/p15.3-release-acceptance-78dbbbf4-8665-4aef-95ef-949fe4eb3019/acceptance.json` |
| Live isolated Windows fixture | Direct text turn rendered; widget moved to non-primary `DISPLAY6` with negative X and different DPI; compact/expanded views and quiet state worked; Core restart/token rotation showed reconnect then restored history; two active tasks showed `2 runs` while a new direct dialogue turn still completed, and activity expanded without exposing IDs by default |

Final archive: `.local/releases/sora-p15.6-acceptance-20260923-r4.zip`,
375,243,885 bytes, SHA-256
`16189cdb338f84c76964fe023f408798dd6be4dc28748ddd76fb021a9846e2e8`.
The packaged widget executable is 116,099,346 bytes, SHA-256
`b4d95e7ad820e330b917857b0336ea502a86c95d6e645a0aa01fdbecc277f43e`.

## Limits and next gate

The live Core fixture used a deterministic dialogue/task provider, so this
proves UI, state and concurrency wiring rather than live-model response
quality. The attachment tests cover selection/preview/composition logic; no
external image understanding or DOCX ingestion is claimed. Notification
behavior is lightweight and local, not a cross-device push system. P15.7
remains the full application/settings stage. P15.2 still needs a physical
paired phone and trusted-certificate acceptance. No commit, tag or staging
operation was performed.
