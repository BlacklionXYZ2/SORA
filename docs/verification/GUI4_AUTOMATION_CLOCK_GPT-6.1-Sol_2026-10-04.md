# GUI-4 scheduling foundation verification

Model name: **GPT-6.1 Sol**. Source checkpoint **2026-10-04 12:23:32 +01:00**, Europe/London. Status: **GUI-4a/c in progress; no active scheduler, persistence/API or GUI acceptance**. [Full contract and next requirements](../gui/GUI4_AUTOMATION_CONTRACT_GPT-6.1-Sol_2026-10-04.md).

## Fresh focused evidence

- Initial isolated `ZoneInfo('Europe/London')` failed because the Windows verification environment lacked timezone data. Added runtime dependency `tzdata>=2024.1,<2027`, updated lock to2026.5, synced `.local/frontend-verify-20261003` only. The owner's `.venv` was not synced or changed.
-29 focused cases passed in0.39s, plus targeted lint/type checks; four schemas exported. Covers one-off boundaries, interval anchors after50 days/JSON restore, daily-versus-elapsed DST, London spring gap and single autumn fold, Samoa whole-day and Lord Howe half-hour gaps, explicit weekly timezone/day selection, invalid/naive/boolean/string/unknown/path-like fields, bounded catch-up/live grace/overlap and evidence-linked occurrence validation.
- Initial test/lint failures were draft formatting and a Lord Howe test boundary already past that local day's scheduled time. The fixture was corrected and rerun; its failing result is not reported as a pass. The Samoa case also validates that gap bookkeeping does not consume the next valid local day's slot.
- Full isolated `./scripts/verify.ps1`, same environment, live exec41461: lint/mypy280 passed,865 tests collected. Terminal completion is recorded below only after the same session finishes. No presumption from startup/progress.

Pure functions evaluate data only: no timer, process start, file writer, repository mutation, API or task dispatch. No C# source/test changed; the previous GUI-3c369-C# checkpoint is historical, not rerun or relabelled here. No native action, device/provider/model call or denied-workflow retry.

Owner Core PID52000/start **2026-09-29 21:49:32**, `.venv/Scripts/sora.exe`, rechecked unchanged at **2026-10-04 12:23:32 +01:00**. AppSettingsv9/UIpreferencesv1/migration11/default Desktop remain unchanged. Dependency/lock/schema source updates do not change that running Core or create installed Automations behavior. Persistence, scheduler lifecycle/recovery/task linking, connected UI and actual scheduled-run acceptance remain required; full goal active.

## Final regression

**2026-10-04 12:26:25 +01:00:** Same exec41461 returned normal terminal exit0. Final-source `./scripts/verify.ps1`: **840 Python passed /25 opt-in skipped in96.42s; 8 PWA passed; mypy280/lint/exported-schema check/compile passed**. Later changes documentation only. No opt-in live/native test is counted as passed and no scheduler/migration/UI acceptance is inferred from this regression.
