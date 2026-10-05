# Editable model-purpose shortlist — GPT-6 Astra

Checkpoint: **2026-10-03 14:53:12 +01:00**, Europe/London.
Status: implemented settings/catalogue/shared Windows UI slice; **live GUI/model acceptance open**.

## User-facing implementation

Full-app **Settings → Go to section → Agents · Codex/Hermes/Antigravity → Model shortlist and
purposes → Edit…** opens the shared descriptive draft editor. Its exact model ID field supports
cached choices and explicit configured IDs; its purpose field is multiline and limited to 500
characters. Add/update puts the fields in the visible draft table. Use draft returns them to
Settings; Save settings atomically persists the list with other changed preferences. Cancel leaves
saved values unchanged. Model-purpose editing does not change the selected default model/effort.

The shared **Agents and models → Edit model purposes…** path uses the same dialog with a **Save
purposes** button that persists only the selected agent's rows. The compact widget already exposes
this catalogue. Revision-check/save failures keep the dialog and draft available. Closing while a
save is pending is fenced. Removal is explicitly from the draft shortlist, not model weights or
provider access. Other provider-listed models remain available for discovery.

The legacy default-model purpose remains a labelled fallback. An explicit matching shortlist row
overrides it and provider text, even if its purpose is blank. Catalogue details show the effective
purpose/source and distinguish provider-listed from configured-unverified entries. Purpose text
is untrusted descriptive data, not permission or a native tool instruction.

These controls compile in both clients but were **not operated or rendered in the failed GUI
attempt below**. This description is implementation evidence, not user-side acceptance.

## Canonical data and discovery

Settings v9 stores `agents.<agent>.model_choices` as bounded arrays of `{id, purpose}` objects.
IDs use the existing exact ModelId contract; extras, duplicate IDs and >64 entries per agent fail
validation atomically. V2–v8 originals are backed up before migration; v7/v8 preferred-purpose
rows are imported without deleting the legacy fallback, disables, destinations or other fields.
Incomplete current v9 config fails validation/reuses valid recovery rather than defaulting access.
The canonical store is bounded to 256 KiB; other legacy file bounds are unchanged.

The existing cached catalogue supplies provider metadata. Snapshots overlay live owner rows and
provide `purpose_source`, `shortlisted` and actual state. Newly configured but unlisted IDs are
`configured_not_checked`, never verified entitlements. No model inference or automatic probe is
needed to edit/read descriptions. Explicit metadata refresh remains separate.

The companion `list_agents` operation now accepts a literal, case-insensitive substring query over
model name, exact ID or purpose, in addition to bounded pages. Continuation belongs to the exact
provider/query listing. Core continues to admit only known exposed refs; selection is pinned to
the associated provider/model, with no arbitrary-ID guessing or silent substitution. Old tasks
retain their model/default pins. Editing descriptions does not revoke current delegated runs.

Disk refresh now advances the settings revision for semantic hand edits and prevents rollback;
old GUI drafts cannot overwrite that newer state using the previous expected revision. This is
separate from the delegation epoch, which is unchanged for purpose-only edits.

## Verification

- Final standard `scripts/verify.ps1`, dedicated `.local/frontend-verify-20261003` environment:
  **649 passed / 24 opt-in skipped**, pytest **92.77 seconds**, **8 PWA passed**, Ruff, mypy
  **252 source files**, generated schemas and compileall passed.
- C#: **43 passed**; full-app and widget builds both **0 warnings / 0 errors** after final UI edits.
- New Python file `tests/runtime/test_model_purposes.py`: **15 cases**, including migration bytes/
  disables/path preservation; duplicate/invalid/excess/extra rows; atomic save; restart and large
  bounded store; hand-edit revision conflicts/rollback; recovery; cached metadata override/removal;
  no discovery/inference side effects; literal query/pagination binding and full-shortlist access.
- Actual loopback HTTP integration saves two rows through `/api/v1/settings`, reads the live
  catalogue, runs controlled local `list_agents` → `delegate`, then verifies the requested exact
  model in the specialist request. The chooser/provider are explicit deterministic fixtures,
  not real small-model accuracy or actual provider entitlement.
- C# tests exercise bounded exact-ID draft update/remove/roundtrip/overflow/duplicate behavior and
  v9 projection parsing. They do not instantiate or operate the WinForms editor.
- Initial full run failed a scheduler test that slept 55 ms and assumed a second sample. Repaired
  it to await the specific sample within one second, keeping all existing assertions; final run
  passed. An initial new HTTP assertion used `content` instead of the actual `response` field;
  corrected the test to the inspected route contract, not the product response.

## GUI attempt and environment

Dedicated offline fixture state `.local/model-purpose-gui-qa-20261003`, loopback Core 18793 and
built SoraDesktop PID 53156. Computer Use observed the initial full-app Chat/navigation, clearly
marked **Offline test model**, zero runs. The first click on Settings failed with
`failed to activate captured window`; fresh returned-window selection and activation recovery
failed identically. Following the Computer Use skill, no further UI input was attempted.

The model-purpose editor was therefore not observed; no claim of its layout, input, save/cancel,
restart, concurrent-modal behavior or compact acceptance follows from compilation/API tests.
This repeated environment limitation leaves that acceptance gate open; it did not prevent the
settings/catalogue/API implementation work recorded here.

QA Core exited normally through its STOP sentinel (exit 0); the verified QA GUI was stopped.
Artifacts retained, port 18793 released, owner sora.exe PID 52000 untouched/alive. No privacy/access
switch changes through GUI, real agent/model inference, installation or user project writes.

## Next gates

1. Full and compact model-purpose editor rendering/input/update/cancel/save/restart, discovery
   refresh preserving drafts, concurrent edits and error retention through the actual GUI.
2. Real local small-model purpose-based model choice and negative/injected intent matrix.
3. Actual provider access/last-success, project/changelog and voice/PWA/delegation acceptance.
4. Remaining planned desktop actions, target/lifecycle/verifier integration and all other open
   frontend checklist rows. No broad completion claim is made.

[Changelog](../../changelog/2026-10-03T145312+0100_W2-W3-MODEL-SHORTLIST-PROGRESS_GPT-6-Astra.md).
