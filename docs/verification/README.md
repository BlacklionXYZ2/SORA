# Verification records

Each file is a **record**: dated evidence written by the named contributor for one phase,
stage or slice. Don't rewrite a record. If evidence changes, add a new dated record and link
it from the living document. Naming is `<ID>_<TOPIC>_<model>_<date>.md`; supporting
artefacts sit in lower-case folders beside the records (for example `p15-integrated-scenarios/`).

Start points:

- The [owner manual-acceptance checklist](OWNER_MANUAL_ACCEPTANCE_CHECKLIST_2026-09-23.md) lists
  checks that only the owner can perform: physical phone, real devices, subjective UI.
- The [frontend alignment tracker](FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md) covers W1–W6.
- For the GUI stages, records are listed per stage in the roadmap's §4.0 table and §12.

## Evidence labels

Records must keep these apart, and a later summary must not merge them:

| Label | Means | Does **not** mean |
|---|---|---|
| Fixture / deterministic | Ran against mocks or synthetic data | Anything about a real model, device or desktop |
| Component | Source plus Python/C#/HTTP/SQLite tests and builds | A rendered, user-operated GUI |
| Native | Real Windows UI/helper exercised | Physical hardware, real model or release |
| Live model / provider | A real model or provider run returned | Entitlement or behaviour for other models |
| Hardware / physical | Real microphone, speaker, phone, monitor or DPI change | Release acceptance |

## Independent-verification ledger

**Owner policy:** work by **Gemini 3.8 Flash** is not trusted on its own claims. A Gemini phase
counts as verified only after a different model has independently audited it with fresh evidence
and recorded the result here. Ledger compiled 2026-10-05 by Opus 5.5 from the plan, changelogs and
these records; the P03A and P06 rows were then updated after Opus 5.5's audit the same day.
Every Gemini phase has now had an independent pass. Open gaps are pinned as strict expected
failures in `tests/verification/`.

| Phase | Gemini 3.8 Flash scope | Independent pass on record | Status |
|---|---|---|---|
| **P03A** | Ten additive contracts; capability registry/resolver, including **scope containment and REMOTE_GUEST rejection**; attention prototype; desktop objects/Kanban base; gestures; social boundary; companion presentation UX | **None.** Later work touched parts of it without auditing the whole: P10.5 (GPT-5.6 Sol, 2026-09-14) extended and tested the attention prototype; P12.6 reuses the resolver; P15.8 (GPT-6) built the canonical Kanban | **Audited 2026-10-05 by Opus 5.5 — live code holds; latent gaps.** Selection-time scope containment and the live Kanban projection hold. `dispatch_capability` does not recheck at execution, and the social module is non-functional; both have no production caller. [Audit record](P03A_P06_INDEPENDENT_AUDIT_Opus-5.5_2026-10-05.md). Original: [P03A record](P03A_COMPANION_CAPABILITY_FOUNDATIONS_2026-09-08.md), [changelog](../../changelog/2026-09-08T130057+0100_P03A_Gemini-3.8-Flash.md) |
| **P06** | Antigravity CLI adapter, rule-based routing engine, dialogue/status fast paths, privacy scope filtering, fallback, steering, adaptive presentation | Partial. GPT-5.6 Sol (2026-09-08 15:17:15) verified only the P05 coding-write integration and a combined 145-test gate, and states it is not a review of Gemini's feature work | **Audited 2026-10-05 by Opus 5.5 — one live privacy gap open.** Local-only tasks can route to Antigravity/Hermes because only Codex counts as cloud; the fallback re-route also drops the flag (latent). Both need an owner decision. Steering fixed; presentation is dead code. [Audit record](P03A_P06_INDEPENDENT_AUDIT_Opus-5.5_2026-10-05.md). Original: [P06 record](P06_ANTIGRAVITY_ROUTING_2026-09-08.md), [closure changelog](../../changelog/2026-09-08T151715+0100_P06-DEPENDENCY-CLOSURE_GPT-5.6-Sol.md) |
| **P07** | Git workspaces, synthesis, review manager, parallel runtime wiring | GPT-5.6 Sol repair and re-verification, 2026-09-09 08:21:49 | **Repaired and re-verified.** [Repair changelog](../../changelog/2026-09-09T082149+0100_P07-REPAIR_GPT-5.6-Sol.md) |
| **P08** | HTTP/1.1 and WebSocket engine, token auth, event replay, projections, extensions | GPT-5.6 Sol repair and re-verification, 2026-09-09 08:21:49 | **Repaired and re-verified.** [Repair changelog](../../changelog/2026-09-09T082149+0100_P08-REPAIR_GPT-5.6-Sol.md) |
| **P09** | Unity overlay and coordinate foundation | Review found the completion claim false ([review and repair](P09_REVIEW_AND_REPAIR_2026-09-09.md), Codex). Later implemented by GPT-6 Astra (incl. Unity 6) and completed by GPT-5.6 Sol (P09.4, 2026-09-16) | **Repaired and completed by other models** |

"Re-verified" refers to the code as it stood on that date. Later phases have changed some of
the same files.

Records by other contributors (GPT-5.6 Sol/Luna, GPT-6, GPT-6 Astra, GPT-6.1 Sol, DeepSeek
V4.1 Flash, Codex) are outside this ledger. Its absence says nothing either way about their
review status. Add a row when the owner asks for another contributor's work to be tracked.

**How to close a row:** audit the phase's behaviour against its acceptance criteria in the plan
(§5), not against Gemini's own report. Run fresh tests, and add or repair tests where coverage
is missing. Write a dated record here and a changelog in your own model name, then update the
row's status. Don't edit the original Gemini records.

## Known record inconsistencies (for the owner)

- Ten changelogs dated 2026-10-02 17:48 to 2026-10-03 09:46 (W1–W6 slices) have filenames ending
  `_GPT-6.1-Sol.md`. Their text credits "GPT-6.1 Astra" or "GPT-6 Astra", and the plan and
  verification records credit GPT-6 Astra. On 2026-10-05 the links that used `_GPT-6-Astra.md`
  names were repointed to the files that actually exist. No attribution text or filename was
  changed; which attribution is correct is the owner's decision.
