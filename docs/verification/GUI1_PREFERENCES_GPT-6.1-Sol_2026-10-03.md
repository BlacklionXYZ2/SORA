# GUI-1a UI preferences, placement and shortcut progress

Model name: **GPT-6.1 Sol**. Checkpoint: **2026-10-03 20:55:19 +01:00**, Europe/London. Status: **implemented slice / in review; GUI-1a remains in progress**. No new whole-stage completion timestamp.

**Final UTF-8 BOM refinement/native import checkpoint: 2026-10-03 21:04:55 +01:00.** Final C# count **80 passed**, three zero-warning/error builds. The initial 78-test checkpoint is retained below; see the addendum for final-source BOM import evidence.

## Delivered scope

- Version-1 readable, UI-only profile store at `desktop-shell/preferences.json`: theme, 85–175% text size, static/reduced-motion preference, Chat compact/pin/detail, allowlisted shortcut, logical outer panel bounds/monitor/DPI and import provenance. No Core settings, tokens, transcript or drafts.
- Strict schema/value/duplicate-key/size/path validation; original-preserving read-only failure; revision/fingerprint checks, cooperating-writer file lock and flushed temporary/atomic replacement. Appearance drafts merge unrelated placement changes but reject competing appearance edits. Explicit recover-defaults backs up original bytes first.
- One-time import of known profile widget/full-app preferences, original/hash/dated-backup preservation and explicit custom legacy-file options. Unknown/corrupt/unrelated canonical JSON is not copied. Legacy quiet/topmost/tab choices remain metadata; no silent pin, no invented DPI or secondary-view parity.
- Native model-independent Appearance / panels with Save/Cancel/reload/placement reset/recovery, dirty-edit Quit guard, live theme/text/pin/detail/compact changes and shortcut re-registration/conflict status.
- Shared panel binding captures native move/resize/hide/close, restores logical monitor-relative bounds, clamps work areas and handles display/DPI notification; system colour/high-contrast refresh hooks. Settings grid rows/headers support larger text.
- All repeat-launch surfaces, including command menus, forward to the primary host. No secondary menu bypasses the profile's theme/text preferences. Core startup/shutdown and the ordinary launcher remain unchanged.

## Fresh component/build/regression evidence

- `dotnet test clients/csharp_tests/csharp_tests.csproj --no-restore`: **78 passed / 0 failed / 0 skipped**. Added 21 preference/options/geometry cases (including theory instances) over the earlier 57-test baseline. Migration tests compare originals/backups byte-for-byte, prove no reimport overwrites later edits, reject canonical/unknown fields, preserve competing files/drafts and recover malformed/null/array/unsupported-version files. Geometry covers 96/144/192 DPI, negative origins and tiny/removed work areas; **simulated geometry, not physical multi-monitor evidence**.
- Shell, full-app and widget builds: **zero warnings/errors** after final source.
- `./scripts/verify.ps1`, dedicated `.local/frontend-verify-20261003`: exit 0; Ruff/schema/compileall pass; mypy **259 files** pass; **686 Python passed / 25 opt-in skipped in 113.83 seconds**; **8 PWA passed**. No Python/Core contract implementation changed in this slice; schema freshness was checked, not regenerated unnecessarily.
- Initial preference test run had six diagnostic-string assertions and one path-normalization assertion fail. Preserved the original read-only diagnostic on rejected Save and normalized the test's Windows path. A subsequent existing mutex test failed because a synchronously waited Task could inline on the owning thread; changed it to a dedicated joined thread. Final suite passes; those failed attempts are not passing evidence.

## Actual Windows user-side evidence

Computer Use operated only generated QA profiles on an unused loopback port **18799**; no QA Core/model/renderer/voice/agent/helper was started. Owner Core **sora PID 52000**, start **2026-09-29 21:49:32**, remained untouched. Native captures were inspected inline, not saved as screenshots.

| Observation | Result and boundary |
|---|---|
| Initial offline host, PID 57372 | Appearance opened without token/Core/inference. Core effects stayed unavailable; UI-only controls worked |
| Native Save | Chose System colours, 150% text and shortcut None. JSON revision advanced and the open panel restyled; large labels wrapped/body scrolled while actions remained reachable |
| Compact/draft | Entered unsent `GUI1 preference test draft — do not send.`; compact control preserved it and standard Close/reopen retained it in the same host |
| Normal Quit/restart | Native Quit left zero QA hosts. PID 26156 restored System, 150%, compact mode and None; draft was empty as intended because drafts are not persisted |
| Move capture | Native title-bar drag changed saved Chat logical x/y from 24/24 to 164/124 at recorded 144 DPI, without losing other preferences |
| Alternate shortcut | CtrlAltSpace was reported conflicted, not claimed active. Saved CtrlAltS successfully registered; native Ctrl+Alt+S reopened hidden Chat without inference |
| One host / menu theme | Repeated final-source menu request exited the secondary; only primary PID 26156 owned it. Menu used saved System/150% styling and all controls were reachable |
| Found focus defect | Unconditional assignment of unchanged TopMost could reorder Chat over Appearance during Save; now only an actual pin change updates it |
| Final-source replay, PID 26400 | Moved Chat bounds restored, shortcut/theme/text restored; explicit Save stayed in foreground Appearance rather than bringing Chat over it. Changing Chat mode updated the clean open preference checkbox |
| Corrupt view, final-source PID 50264 | Unsupported version-2 file showed safe in-memory defaults and precise diagnostic; Save and placement reset disabled; legacy import explicitly not attempted; recovery available |
| No-write corrupt cleanup | Normal Quit preserved original SHA-256 **DA4E655772005738EA85C7512BDA645CF451AF55D3E166FE6968172ABAAAF6AE** through both diagnostic runs |

The first native Quit attempt hit a stale cached accessibility element. Refreshed the returned menu binding/screenshot and used one coordinate retry; later authoritative process checks confirmed shutdown. Immediate inventory/capture can precede event processing; settled observations were used before reporting Save/Close success. No force-kill, terminal UI automation, privacy/security change or Windows-key shortcut was used.

The Computer Use skill requires action-time confirmation for replacing/resetting local data. **Recovery/reset replacement buttons were not operated**; backup/recovery correctness is component evidence, while the visible no-write diagnostic/disabled controls are actual GUI evidence. No discard of an unsaved preference draft was automated.

## Cleanup and remaining gates

Final checks: **zero SoraShell processes**, no listener on 18799, unchanged owner Core PID/start time, five reference files match manifest bytes/SHA-256 and no overview diff. QA preference fixtures remain under `.local/gui1-preferences-offline-20261003` and `.local/gui1-preferences-corrupt-20261003`; they contain only synthetic UI data and are not release assets.

Managed profile discovery/startup/readiness/owned graceful shutdown, helper-preserving launcher integration and canonical offline recovery are still required. Broader existing-owner preference import and native repair/reset acceptance, physical 100/200% and mixed monitors, monitor removal/sleep/fullscreen, OS text scaling, actual high contrast and screen-reader testing remain open. Legacy quiet/tab behavior depends on retained workflows, not metadata alone.

GUI-1b/c/d production Chat/attachments/IME/scroll/activity/secondary surfaces/voice and GUI-2 full Settings remain unfinished. Memory graph, scheduler and semantic avatar-panel interaction are not delivered by this preference work. The GUI-0 fixture Stop/real-model acceptance boundaries remain as in earlier evidence; this turn did not send a model prompt.

[User/developer runbook](../runbooks/SORA_DESKTOP_SHELL.md) · [Root roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Earlier host evidence](GUI1_HOST_GPT-6.1-Sol_2026-10-03.md).

## Final-source BOM migration addendum — 21:04:55 +01:00

The existing widget writer can emit UTF-8 BOM bytes. Parsing now skips only that encoding marker, while hashes/backups retain all original bytes. Two new tests cover recognized legacy BOM and valid UI-store BOM; **80 C# passed** and all three Windows builds remain zero-warning/error. Python/PWA source was unchanged, so the preceding full gate was not redundantly rerun.

Actual native profile `.local/gui1-preferences-import-20261003`, PID 50476, started with a byte-verified **EFBBBF** legacy widget file: old topmost/quiet true, compact true, technical detail true, retired monitor and physical coordinates -5000/50000. Appearance reported one recognized imported file; compact/detail checked, pin unchecked, quiet/tab metadata and DPI limitation clearly labelled. Opening Chat displayed a fully reachable 144-DPI compact panel rather than restoring out-of-range coordinates. This is actual fixture migration/rendering, not physical monitor unplug or owner-profile migration.

Original/backup/provenance SHA-256 all **820E2CB5DF67DA2869336FFB8E92F7A34CA4D1F07DE74D26E8085F77005CA9E8**. Native Quit completed normally; source/backup and earlier invalid-file hashes remained unchanged, zero QA shells/listeners, owner Core PID/start preserved. All three generated QA profiles are retained under `.local` as synthetic evidence. No privacy/security/repair/reset or inference effect was operated.
