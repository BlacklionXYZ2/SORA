# W2/W3 editable multi-model purposes — GPT-6 Astra

Implementation/verification checkpoint: **2026-10-03 14:53:12 +01:00**, Europe/London.
Status: **implemented progress slice; user-side acceptance open**. No broad workstream or frontend
goal closure. Existing contributor edits, historical logs and owner processes were preserved.

## Implemented changes

- Canonical settings v9 adds up to 64 exact model-ID/purpose rows per agent, with unique IDs,
  ModelId validation, 500-character purpose bounds, strict extras rejection and atomic save.
  These rows are descriptive preferences, not credentials, permissions or a new provider store.
  Other provider-listed models remain discoverable; default model/effort is unchanged by editing.
- Settings v2–v8 migrate to v9 with original-byte backups. v7/v8's preferred model-purpose is
  copied into a shortlist row when both are nonempty; the original fallback field is also retained,
  including orphan descriptions. Disables, paths, modes, base refs and other preferences survive.
  Incomplete current v9 records do not masquerade as a migration; existing recovery stays active.
- Raised the canonical settings-file bound from 16 KiB to 256 KiB for bounded multi-model lists;
  oversized files are rejected without an unbounded read. Legacy model/other-store bounds were
  not changed. Hand-edited model-purpose JSON uses the same model validation/refresh path.
- Catalogue snapshots merge owner rows over cached provider descriptions without mutating the
  cache or probing models. Purpose source and shortlist flags are explicit. Saved unlisted IDs
  are labelled `configured_not_checked`, never `provider_listed` or verified entitlement.
- SORA's existing companion discovery now receives those purposes/rows. Added a bounded literal
  name/ID/purpose query to `list_agents`; continuation cursors bind provider and query. This can
  find a model anywhere in a large shortlist without dumping it into the small model's prompt.
  Known/exposed-reference checks and exact provider/model delegation remain intact.
- Added shared Windows draft controls: Settings → agent → Model shortlist and purposes → Edit;
  and Agents and models → Edit model purposes (also reachable from the compact widget catalogue).
  Model ID dropdown/text plus multiline purpose supports add/update/removal from the draft.
  Settings uses Use draft then Save settings; catalogue uses revision-checked Save purposes.
  Failed catalogue saves retain the dialog/draft; close is fenced while saving. Untaken editor
  changes disable acceptance until Add/update. Cancel does not save.
- Shared catalogue details display effective purpose, source and actual listed/configured state.
  Settings supports the custom list field rather than a raw JSON textbox. Client parsing now
  recognizes v9; structural JSON comparison prevents whitespace formatting marking rows changed.
  Parent Settings re-render is suspended while its purpose modal is open, preserving draft/conflict
  behavior during concurrent projections.
- Fixed disk-refresh revisions: semantic edits without a manually bumped revision now advance it;
  lower revisions cannot roll back the conflict fence. Descriptive edits do not increment the
  delegation epoch or cancel existing agent work. Existing queued task/model pins remain intact.
- Added 15 Python purpose/migration/cache/filter/API regression cases and two C# draft tests,
  expanded client version coverage, exported settings/companion schemas and updated the example.
- Fixed an unrelated flaky scheduler regression encountered in the full gate: wait for the second
  sample under a one-second deadline instead of assuming an exact 55 ms sleep. The one-inference,
  no-foreground-work and shutdown assertions remain unchanged.

## Verification and limits

- Final `scripts/verify.ps1` with `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003`:
  **649 Python passed / 24 opt-in skipped**, **8 PWA passed**, Ruff, mypy **252 files**, schema
  check and compileall passed. Final pytest elapsed **92.77 seconds**.
- C# tests: **43 passed**. Both Windows clients build with **0 warnings / 0 errors** after final
  source changes. Tests cover the pure draft, not actual WinForms input/rendering.
- Actual authenticated loopback HTTP test saves two purposes, reads the catalogue, runs the
  controlled companion query/delegate path and proves the selected exact model reaches the
  deterministic specialist request. No real model/provider inference or entitlement was tested.
- Migration preserves original bytes and disables/paths; tests cover atomic invalid rows, duplicates,
  size bounds, >16 KiB lists, save/restart/hand-edit refresh, revision conflicts/rollback, recovery,
  metadata override/removal, no implicit probe and literal filtered pagination/exposed references.
- Computer Use captured the isolated full app in Offline test mode. Clicking Settings failed with
  `failed to activate captured window`; fresh selection/activation recovery failed too. The skill
  required stopping UI input. **No new editor rendering, input/save/restart or compact-widget GUI
  acceptance is claimed.** This is the second goal-turn activation limitation, not a code impasse;
  meaningful implementation and API/regression progress continued.
- Isolated QA state `.local/model-purpose-gui-qa-20261003` was retained. Its Core exited normally
  via STOP sentinel (exit 0). The verified QA GUI PID 53156 was stopped after activation failed;
  port 18793 released. Owner Core `sora.exe` PID 52000 was not restarted/reconfigured and remains
  alive. No GUI privacy/security toggles, real LLM calls or user project writes were performed.

## Open work

Actual full/compact model-purpose editor input/save/cancel/restart and concurrent-edit acceptance;
real local small-model purpose-based selection/negative-intent accuracy; remaining native action
executors/verifiers and full lifecycle; actual specialist entitlement/last-success evidence; prior
project/changelog/live/voice/PWA/other acceptance gates. The full frontend goal remains active.

[Evidence](../docs/verification/W2_W3_MODEL_PURPOSES_GPT-6-Astra_2026-10-03.md).
