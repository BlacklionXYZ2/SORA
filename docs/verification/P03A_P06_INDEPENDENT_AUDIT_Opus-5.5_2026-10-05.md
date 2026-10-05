# P03A and P06 — independent audit of Gemini 3.8 Flash's work

Auditor: **Opus 5.5**. Audit completed **2026-10-05**, Europe/London, at the owner's request
("finish off the checks"). This is the first independent audit of P03A, and of P06 beyond the
P05 handoff that GPT-5.6 Sol closed on 2026-09-08.

Method: each acceptance criterion in [the plan](../../SORA_IMPLEMENTATION_PLAN.md) §5 P03A.1–.6
and P06.1–.5 was checked against the current source, not Gemini's report. I traced every module
to its production callers, read the existing tests to see what they actually prove, and wrote
executable evidence in
[`tests/verification/test_gemini_p03a_p06_audit.py`](../../tests/verification/test_gemini_p03a_p06_audit.py).
Confirmed gaps are pinned there as `xfail(strict=True)` tests. Each was re-run with
`--runxfail` to confirm it fails for the stated reason, and any of them starting to pass will
fail the suite. No live provider, native desktop or hardware check was involved.

## Summary

| Area | Verdict |
|---|---|
| Live production code from Gemini | **One real privacy gap (P06.2).** Everything else that is live behaves correctly |
| Gemini's tests | Mostly assert what the code does, not the criterion. Several criteria were never exercised |
| Gemini's reports | Two factual inaccuracies (below) |
| Dead code | `dispatch_capability`, the social module and `present_result` have **no production callers**; their gaps are latent |
| Fix applied | P06.4 steering that names two specialists now asks for clarification |

## Findings by criterion

| Criterion | Result | Evidence |
|---|---|---|
| P03A.1 contracts | **Holds**, with an inaccurate report. Gemini's changelog says `CapabilityDescriptor` has "risk level, required grants, timeouts, and idempotency guarantees". The model has none of those fields | `src/sora/contracts/models.py` `CapabilityDescriptor` |
| P03A.2 bounded relevance | **Holds.** Scoring is keyword-based and budgeted, and the manifest gives a reason for every exclusion | Existing `test_large_synthetic_registry_bounded_selection` |
| P03A.3 scope at selection | **Holds.** `LOCAL_RESTRICTED`, `NETWORK_PUBLIC` and `REMOTE_GUEST` are all contained | New `test_p03a3_resolver_contains_every_scope` |
| P03A.3 recheck at execution ("revocation/expiry/disable/scope change between selection and execution denies action") | **Not met; latent.** `dispatch_capability` checks set expiry and grant status only. It never rechecks scope, never compares `resolver_revision`, never consults the registry, and accepts a grant issued for any other resource. **It has no production callers**: the live resolver uses (direct-dialogue task status, Sol's P12.6 desktop-object affordances) are read-only or rely on Sol's exact grants. No API accepts a client-supplied active set | Strict xfails `test_p03a3_dispatch_rechecks_scope_after_selection`, `test_p03a3_dispatch_rejects_grant_for_another_resource`. Gemini's dispatch tests inject capabilities with `model_copy`, bypassing the resolver |
| P03A.4 companion activity/steering | **Holds after fix.** See P06.4 | — |
| P03A.5 attention/objects | **Holds.** Attention expiry was rebuilt and is tested by Sol (P10.5). The Kanban projection, which is live, maps all 12 task statuses correctly | New `test_p03a5_kanban_maps_every_task_status` |
| P03A.6 social / extensions | Extensions **hold**: unknown IDs in `extensions.json` are ignored and activation requires persisted grants (Sol's P08 repair). Social is **dead code with two defects**: ingested events are tagged `ContextSource.MEMORY` and owned by the network name, so the compiler always drops them (`owner_scope_mismatch`). "Cannot become FACT" therefore holds only vacuously, and Gemini's test never passed the item through the compiler. The public profile bio is `persona.md`'s first line (`# Persona`) | `test_p03a6_social_events_never_reach_compiled_context`; strict xfail `test_p03a6_public_profile_bio_is_not_a_private_file_line` |
| P06.1 Antigravity adapter | **Works; docstring was false.** It claimed in-place writes "remain disabled until worktree isolation". In fact the adapter grants its `cwd` with `--add-dir`, and `--dangerously-skip-permissions` can be passed. In auto mode `cwd` is the scratch `<root>/workspace`, which limits what it can touch by default | Docstring corrected (comment only) |
| P06.2 routing respects privacy | **Not met; live.** The router's default `cloud_providers` is `{"codex"}`, so **Antigravity (Google-hosted) and Hermes count as local.** Production marks private editor selections (`service.py` `submit_editor_task`), private screen references (`submit_referenced_task`) and API `is_local_only` tasks as local-only, and these can be routed to Antigravity or Hermes | Strict xfail `test_p06_local_only_task_is_not_sent_to_a_hosted_specialist` |
| P06.3 no cloud fallback for local-only | **Not met; latent.** The fallback re-route in `SoraRuntime._execute` calls `route(request.intent)` without the privacy flag, and `TaskRecord` does not persist `is_local_only`. It cannot leak today only because no provider the router calls cloud appears in a fallback list. It becomes live as soon as P06.2 is fixed, so **both must be fixed together**. `run_fanout` likewise records `is_local_only` in a trace but never filters by it (no production caller) | Strict xfail `test_p06_fallback_keeps_local_only_privacy` |
| P06.4 steering | **Fixed.** Names were matched in a fixed order, so "cancel the Hermes task, not Codex" resolved to the Codex task. Voice `CANCEL_TASK` uses this path. Naming more than one specialist now returns no target, so voice asks "Which active task or specialist do you mean?" and text steering reports the target as ambiguous | `test_p06_4_steering_naming_two_specialists_requires_clarification` |
| P06.5 adaptive presentation | **Latent defect; dead code.** `present_result` has no production caller. It credits any result without a patch to "SORA", and it does not carry uncertainties into the presentation | Strict xfail `test_p06_5_presentation_keeps_specialist_authorship` |

## Decisions needed from the owner

1. **What "local-only" means.** Should private editor/screen context ever go to hosted
   specialists (Antigravity, Hermes, Codex)? If not, set the hosted providers as cloud and fix
   the fallback re-route at the same time (P06.2 + P06.3). Local-only tasks would then run only
   on local providers, which today means the deterministic fixture. If yes, the "local-only"
   label and the plan's privacy criterion should be changed to say so.
2. **Dead P03A/P06 code.** Either harden `dispatch_capability`, the social module and
   `present_result` before anything calls them, or mark them as unused prototypes.

## Verification run

- `pytest tests/verification/test_gemini_p03a_p06_audit.py`: 4 passed, 6 strict xfailed.
  With `--runxfail`, all 6 fail with their stated assertion.
- Full gate after the fix (2026-10-05): `ruff check` clean; `mypy` strict clean (286 files);
  `export-contracts.py --check` passed; `pytest` **908 passed / 25 opt-in skipped / 6 xfailed**;
  `compileall` OK.
- Same day, unchanged by the fix: `dotnet test` 369/369; zero-warning builds of
  desktop_shell, desktop_app and desktop_widget; `verify-pwa.ps1` 8/8.
- Not run: live Antigravity/Hermes/Codex, native desktop, hardware.
