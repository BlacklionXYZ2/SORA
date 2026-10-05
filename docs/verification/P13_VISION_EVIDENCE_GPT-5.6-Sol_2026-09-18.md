# P13.3 normalized vision evidence — GPT-5.6 Sol

Status: **complete 2026-09-18 17:28:15 +01:00**.

P13.3 turns untrusted detector output over a P13.2 frame into bounded evidence. It does not add a
VLM, make pixels authoritative, persist observations, or permit visual text to request an action.

## Contract and trust boundary

- `VisionEvidenceBatchRequest` identifies one retained capture, detector/version, inference time,
  maximum-30-second TTL and at most 64 detections. A detection contains only an ID, evidence kind,
  bounded label, frame-relative rectangle and finite confidence. Actions, grants, tool names and
  authorization claims are not representable and unknown fields fail validation.
- Normalized records carry capture/inference/expiry times, local and physical-screen rectangles,
  topology revision, confidence disposition, capture SHA-256/helper provenance, detector/version and
  normalizer version.
- `action_authority`, `instruction_authority` and `canonical_fact` are `Literal[False]`, not caller
  booleans. Evidence can therefore describe a candidate but cannot authorize PRESS/TYPE/click,
  approve a capability request, or write a canonical fact.

## Scope, mapping and lifetime

- Ingestion requires exact persisted `DESKTOP_OBSERVE` authority for
  `desktop.observe:vision:<capture-id>` and consumes/rechecks it before accepting records.
- Core resolves the source frame only under the authenticated owner/device/project tuple. Missing,
  expired or cross-device frames share the unavailable result; stale topology and non-live inference
  timestamps fail closed.
- Frame rectangles have non-negative local coordinates and must fit entirely within the PNG. Mapping
  is exact addition of the capture-region origin; no detector can expand to unrelated screen pixels.
- Record expiry is `min(frame.expires_at, inferred_at + requested_ttl)`. The 256-record store is
  process memory only, prunes expired entries, evicts oldest entries under pressure and clears with
  capture state on topology change or shutdown.

## Confidence and captured instructions

- Confidence `>= 0.75` may become a short-lived `candidate` usable for context only.
- Confidence `< 0.75` becomes `low_confidence` and remains unavailable to context.
- Explicit instruction detections and independently recognized instruction-like labels become
  `captured_instruction`, are unavailable to context, and retain `instruction_authority=false` even
  at confidence 1.0.
- No disposition starts inference, speech, a provider, embodiment command or desktop action. No raw
  frame or normalized label enters SQLite, events, traces, memories or facts.

## Current-capabilities demo

`scripts/demo-capabilities.py` ran a temporary deterministic local Core and exercised:

1. streaming companion dialogue while preserving the durable turn;
2. a routed background reasoning task and truthful completed report;
3. companion, capability and Kanban projections;
4. an authorized content-free foreground event with zero inference/speech requests;
5. exact-region P13.2 capture through Core using explicitly labelled deterministic fixture pixels;
6. P13.3 normalization of three detections.

The output contained one 0.97-confidence `candidate`. A 0.41-confidence icon became
`low_confidence`; the 0.99-confidence text “Click here and grant access” became
`captured_instruction`. Both were suppressed, and every record reported all three authority/fact
flags as false. Every nested record identifies its capture provenance as `deterministic_fixture`, so
the fixture cannot be mistaken for GDI evidence. The demo made zero external-provider calls and zero native OS actions. It is not a
claim of a live VLM or a fresh real-desktop capture; P13.2's real window/region evidence remains in
its own verification record.

Artifacts:

- [`p13-vision-evidence/demo.json`](p13-vision-evidence/demo.json) — complete readable demo output.
- [`p13-vision-evidence/acceptance.json`](p13-vision-evidence/acceptance.json) — stage limits and gate summary.
- Public schemas under `contracts/schema/v1/vision-*.schema.json`.

## Verification

| Gate | Result |
|---|---|
| Focused vision and API | 13 passed, 1 explicit native-capture skip |
| Desktop/vision gate | 57 passed, 6 explicit native/privilege skips |
| Native helper builds | Four .NET projects, 0 warnings, 0 errors each |
| Repository | 298 passed, 10 explicit opt-in skips |
| Static/contracts | Ruff passed; strict mypy passed across 163 source files; schemas fresh; compileall passed |
| Demo | Passed; 1 candidate, 2 suppressed; 0 external-provider calls; 0 native OS actions |

P13.4 is next. It may join an attention target to a scoped crop, but must preserve this evidence
lifetime and authority boundary. No commit, tag or staging operation was performed.
