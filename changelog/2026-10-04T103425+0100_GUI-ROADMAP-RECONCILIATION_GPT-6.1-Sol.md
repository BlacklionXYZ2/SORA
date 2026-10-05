# GUI roadmap current-source documentation reconciliation

Model name: **GPT-6.1 Sol**. Documentation checkpoint: **2026-10-04 10:34:25 +01:00**, Europe/London. Status: **documentation update; GUI stages remain in progress**. This timestamp is not a stage-completion time.

## Changes

- Updated `SORA_GUI_IMPLEMENTATION_ROADMAP.md` to v1.27. Reconciled the header, Memory reuse row, architecture pointers, semantic Memory requirement, GUI-3c checklist/sequence and next-work handoff with inspected working-tree source.
- Added §4.28 covering existing `find_memory`/`present_memory`, issued canonical references, actual context-selection events, turn-aware acknowledgement waiting/cancellation, Memory chip projection/navigation and the immediate pre-selection pending check. Marked earlier unconnected wording historical rather than rewriting contributor evidence.
- Distinguished source integration from recorded passing verification and actual native/live acceptance. The earlier 788-Python/349-C# transport checkpoints predate later source and are not reused as proof of current final-source correctness. The deterministic companion test file is recorded as source, not a freshly passing suite.
- Specified the next implementation scope: harden/test the existing GUI-3c integration, check/export schemas, complete isolated regression/build/launcher checks and obtain connected native/live acceptance. Then proceed with persisted scheduling, real graph/design and release parity according to unchanged dependencies.
- Reconciled the desktop-shell runbook's current Memory guidance with the same boundaries. Preserved raw-ID versus issued-target semantics, exact-version chip navigation, static local-policy direction, no capture/private-thought claims and no success from pending dispatch.

## Scope and verification

Documentation-only changes: the roadmap, desktop-shell runbook and this new model-named changelog. No implementation, tests, settings, schema export, launcher, database or runtime mutation; no owner restart/reload, native workflow retry or provider call. The product test suite is not rerun in this pass.

GUI-0a/0c/0d retain their original completed-scope timestamp **2026-10-03 19:24:55 +01:00**. GUI-0b review and GUI-1–GUI-6 acceptance remain open. Original overview/design/draft/assets, existing logs and contributor attribution are preserved. AppSettingsv9, UIpreferencesv1 and default Desktop are unchanged.

## Completed documentation validation

**2026-10-04 10:39:34 +01:00:** Checked149 local links across the roadmap, runbook and this log; zero broken. All five manifest reference assets match their recorded byte sizes and SHA-256 hashes. Exactly the original three completed-stage checkboxes and their19:24:55 timestamps remain. `git diff --check` returned exit0 for tracked differences; the new/untracked documentation is additionally covered by the explicit link/asset/fingerprint checks, not falsely included in Git's tracked whitespace coverage.

The immediate pre-edit fingerprint contains1035 repository-visible files (excluding `SORA.zip` and `uv.lock`). Comparison found exactly two declared existing-file changes (roadmap/runbook),1033 byte-identical existing files, no missing files and only this new changelog. Product source/tests and all pre-existing contributor logs, overview, preserved draft and original references remain byte-identical to that pre-edit snapshot. No commit, reset or material deletion.
