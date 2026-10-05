# W2 agent preferences — GPT-6 Astra

Slice completed: **2026-10-03 09:46:29 +01:00** (Europe/London).
Status: preference slice implemented and verified; W2/W3 and overall frontend goal remain in progress.

## Implemented

- Unified settings v7 adds typed per-Codex/Hermes/Antigravity enable flags, provider purpose,
  preferred exact model ID, supported preferred effort and preferred-model purpose. No second store.
- v2–v6 migration preserves the original; complete v7 agent preferences are required on disk.
  Store writes enforce the same 16 KiB bound as reads before replacing canonical settings.
- Schema-driven Windows Settings provides agent sections, editable model dropdowns and explicit
  no-inference metadata refresh. Cached choices and unsaved drafts survive refresh/save.
  Partial discovery errors name unavailable agents without leaking raw backend errors.
- Catalogue projects enabled state, saved preferences/purposes and effective defaults independently
  of native model metadata. Both clients' task selector shows the saved preference and disabled state.
- Owner-local new tasks/board starts pin saved preferences into TaskRecord/ProviderRequest.
  Explicit model selection does not inherit a possibly incompatible preferred-model effort.
  Preferences do not mutate provider config, queued task selection or retry selection.
- Per-agent enable changes use the existing shared delegation epoch: conservatively revoke all
  outstanding owner-local delegation, reject disabled admission/retry/steer, and recheck at launch.
  A native cancellation request is not treated as verified process exit.

## Automated evidence

Final `scripts/verify.ps1` using `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003`:
**603 Python passed / 24 opt-in skipped**, 115.41 seconds; Ruff, mypy (243 files), generated-contract
check, compileall and **8 PWA checks** passed. Contract export was run before the gate.

**41 C# tests** passed; full app and compact widget built with zero warnings/errors.
Ten new preference tests cover migration/backups, invalid effort/model rejection with unchanged
disk, live/restart preferences, complete-v7 validation, new/board task pins, explicit override,
catalogue projection without discovery and actual fixture active/queued disable/re-enable revocation.
Existing global revocation tests also remain green. This is fixture execution, not paid inference.

An earlier full gate found the shipped example still at v6; corrected to v7 and reran the gate.
GUI review also identified discovered-choice loss on save; retained choices and re-reviewed the fix.

## User-side evidence

Computer Use reviewed only owned QA full-app processes **12348** then **42916**, with isolated Core
port **18793**, state `.local/agent-preferences-qa-20261003`, no owner settings/conversation changes.

1. Agent sections/fields and metadata refresh are visible in Settings at the normal compact full-app size.
2. Actual native metadata discovery again returned Codex 7, Hermes 22, Antigravity 18 entries.
   The Settings Antigravity dropdown displayed all 18 exact IDs.
3. GUI selected `gemini-3.8-flash-low`, entered `Low-cost research and quick desktop questions`,
   and saved. Disk contains settings v7, revision 1, delegation epoch 0 and those exact values.
4. Restarted the owned QA Core and rebuilt GUI. The preferred ID and purpose were restored visibly;
   restarted catalogue proof also contains the preference. No specialist inference was launched.
5. Final rebuilt GUI metadata refresh followed by Save preserved the dropdown options; opened
   dropdown visibly retained the full native list and selected low-tier ID.
6. QA GUI closed and verified absent; owned QA Core tree stopped and port released. Owner Core
   PID **52000** remained alive. Core QA restart/cleanup was forced, not graceful-shutdown acceptance.

Private QA metadata evidence remains in `.local/agent-preferences-qa-20261003/catalogue-proof.json`.
No token/credential output, auth changes, live specialist prompt, Unity changes, audio/device test
or fresh compact-widget GUI acceptance occurred in this slice.

## Remaining scope and GUI criticisms

One preferred model/purpose per harness is delivered, not the full editable multi-model shortlist
required for a compact 2B-facing purpose catalogue. General CompanionCall/delegation orchestration,
real project choices/writer-lease UI, task follow-up/progress/cancel acceptance and last-success/live
entitlement remain open. Broad frontend/native/voice/avatar/memory/DPI requirements stay active.
Long purpose text currently uses an editable single-line field; it is inspectable but a dedicated
shortlist/purpose editor should improve readability. Last-section jumps can show the preceding
section because the scroll area cannot scroll past its content end; all fields remain scrollable.
The owner's already running Core was not restarted, so it has not loaded this new source slice.
