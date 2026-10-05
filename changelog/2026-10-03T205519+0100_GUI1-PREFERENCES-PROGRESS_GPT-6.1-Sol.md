# GUI-1a preferences/placement/shortcuts progress — GPT-6.1 Sol

Model name: **GPT-6.1 Sol**. Checkpoint: **2026-10-03 20:55:19 +01:00**, Europe/London. Status: **implemented slice / in review; GUI-1a in progress**. No new whole GUI stage is marked complete.

Final-source UTF-8 BOM/native import addendum at **21:04:55 +01:00**: **80 C# passed**, original/backup byte preservation and actual retired-monitor fixture migration checked. [Separate dated addendum changelog](2026-10-03T210455+0100_GUI1-PREFERENCES-BOM_GPT-6.1-Sol.md). The initial 78-test checkpoint below remains historical, not the final count.

## Implemented changes

- Added `clients/desktop_shell/ShellPreferences.cs`: UI-only versioned records, logical geometry, strict/bounded original-preserving store, revisions/file fingerprints/atomic writes, one-time recognized legacy import with byte-identical dated backups and explicit recovery.
- Added `PanelPreferencesBinding.cs`: shared font/theme/pin application, captured logical panel placement, monitor/DPI/work-area restoration/clamping, disposal cleanup and passive z-order preservation.
- Added `AppearanceForm.cs`: native offline-capable appearance/panel/shortcut controls, retained edit/conflict behavior, Save/Cancel/reload, explicit reset/recovery and dirty-edit Quit decisions. Invalid files disable writes; Core model/access/voice/agent settings stay canonical.
- Updated `ShellHost.cs`: preference ownership, independent Appearance window, bindings, dynamic hotkey/recovery status, display/system-colour notification and owned resource cleanup. Attached Core ownership remains unchanged.
- Updated `Program.cs`, `ShellProfile.cs`, `ShellInstance.cs` and `CommandMenuForm.cs`: bounded Appearance/legacy-import entry options; repeat launches forward all surfaces to the primary host rather than creating differently styled secondary menus.
- Updated `ShellForm.cs` and `ShellTheme.cs`: shared compact/detail preferences, live dark/system palette and enlarged native text/grid support; no fake response stream or new Core runtime.
- Added `ShellPreferencesTests.cs` and linked source in the C# test project; repaired `ShellHostTests.cs` to use a real secondary thread rather than a potentially inlined task for thread-affine mutex coverage.
- Updated roadmap/host-spec progress; added a desktop-shell runbook and [fresh evidence](../docs/verification/GUI1_PREFERENCES_GPT-6.1-Sol_2026-10-03.md). Existing contributor logs/reference originals/completion dates preserved.

## Verification and GUI-driven repairs

Fresh gate: **686 Python passed / 25 opt-in skipped**, **8 PWA passed**, Ruff/schema/compileall passed and mypy **259 files** passed; dedicated QA environment, exit 0. Final C# **78 passed**; all three Windows clients **zero warnings/errors**.

Actual offline native UI: Save/system colours/150% text, compact unsent-draft hide/reopen, normal restart persistence, moved bounds, shortcut conflict/alternate registration/summon, primary-host menu styling, clean cross-panel preference sync, focus-preserving Save and invalid-file disabled-write diagnostics. GUI tests caught/repaired unchanged-TopMost z-order churn, stale clean controls, mismatched secondary-menu styling and misleading invalid-store import wording. Initial assertion/test-thread failures and one stale native element recovery are recorded, not counted as passes.

Native reset/recovery replacements were not clicked because the Computer Use skill requires action-time confirmation for local-data replacement; byte-preserving replacement is tested at component level. Physical multi-monitor/high-contrast/screen-reader/fullscreen/voice/model/provider acceptance is not claimed.

Cleanup: no QA host or listener; owner Core PID 52000 retained its original start time; corrupt synthetic file retained its SHA-256; five reference assets still match originals. No owner configuration/model/renderer change, ordinary-launcher replacement, stage closure, commit/reset, force kill or goal-status change.

## Next

Finish GUI-1a managed discovery/helper-preserving startup/owned graceful shutdown and broader preference/placement acceptance. Then production Chat/attachments/IME/scroll, retained secondary workflows and voice integration; full Settings, Memory, Automations and final visual completion remain required.
