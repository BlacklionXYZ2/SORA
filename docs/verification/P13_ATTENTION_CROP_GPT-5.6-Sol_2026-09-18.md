# P13.4 attention-target cropped fallback — GPT-5.6 Sol

Status: **complete 2026-09-18 17:44:14 +01:00**.

P13.4 completes Phase 13 by joining P10's volatile circle target/reference path to the bounded P13.2
capture and P13.3 evidence paths. Semantic UI Automation remains the default; vision is an explicit,
short-lived fallback for a geometric circle that has no semantic desktop target.

## Request and semantic-default boundary

- `AttentionCropFallbackRequest` contains a request ID, attention-target ID, capture ID, a fixed
  `uia_insufficient` reason and a maximum-30-second TTL. It cannot carry a rectangle, PNG, cursor
  samples, action, grant or authorization claim. Unknown fields fail validation.
- Core resolves `reference:<attention-target-id>` only in the authenticated owner/device/project
  scope. It requires source `circle`, a live spatial expiry, current topology, a physical rectangle
  and no `desktop_target_id`.
- A circle already backed by a P10 semantic desktop target is rejected before capture or grant use.
  Hover, click and selection targets are also rejected. This keeps UIA and existing app integrations
  ahead of vision.

## Exact crop and lifecycle

- Core derives the crop rectangle from the stored circle reference; callers cannot widen or replace
  it. P13.2 then requires its exact `desktop.capture:region:<revision>:<rect>` `DESKTOP_OBSERVE`
  grant and performs one frame.
- The reference is resolved again after capture. If it expired, was invalidated, changed geometry,
  changed scope or changed topology during native work, the returned frame is removed and no crop
  link is created.
- Crop, enriched attention target and reference share the earliest source/capture expiry. The exact
  crop ID, timestamp, region, SHA-256 and source provenance remain inspectable; no broader desktop
  frame is requested.
- Crop/reference joins are volatile and clear with capture/evidence state on topology change or
  shutdown. A target can receive one scoped crop; repeated capture attempts fail closed.

## Evidence and task reuse

- When P13.3 normalizes the linked crop, Core copies only IDs for evidence marked
  `usable_for_context` onto the reference. Low-confidence and captured-instruction IDs are not linked.
- A referenced task stores the minimal target rectangle, crop ID and usable evidence IDs. It does not
  store the PNG, cursor trajectory or detector record/label.
- During immediate local task execution, still-live usable evidence records are read from the
  owner/device/project-scoped in-memory store and compiled as private `VISION_EVIDENCE_V1` context.
  Expired, cross-crop, low-confidence and instruction evidence is skipped. The context manifest may
  name the evidence ID, but traces do not contain its label or pixels.
- These references remain non-authoritative. Crop or detector evidence does not confer PRESS, TYPE,
  click, grant, fact or memory authority.

## Acceptance fixture

The integration fixture submitted 33 current-topology cursor samples forming a geometrically accepted
circle. P10.5 resolved the exact rectangle `(340, 240, 120, 120)` and P10.6 remembered it. P13.4:

1. derived that rectangle without accepting caller geometry;
2. sent exactly the 120×120 region to the deterministic capture bridge;
3. returned one timestamped/digested frame and an enriched target/reference with the same expiry;
4. normalized a 0.94-confidence “Unlabeled status panel” candidate plus a 0.99-confidence captured
   instruction;
5. linked only the useful candidate ID;
6. reused the reference in a deterministic background task, where only the useful live evidence
   label appeared in transient provider context.

SQLite byte inspection found neither the 33 monotonic cursor values, PNG/base64 data, the useful
detector label nor the captured instruction. A separate in-flight test invalidated the spatial
reference while capture was blocked; Core discarded the completed frame and retained no evidence.
Semantic-backed and non-circle targets made zero bridge calls and consumed no grant use.

The capture pixels in this new integration test are deterministic fixture pixels. P13.2's previously
recorded real window and exact-region native capture remains the hardware evidence; this run does not
claim a fresh live-desktop or VLM test.

## Verification

| Gate | Result |
|---|---|
| P13.4 acceptance | 4 passed |
| Attention/reference/vision/API focus | 37 passed, 1 explicit native-capture skip |
| Desktop/vision gate | 61 passed, 6 explicit native/privilege skips |
| Native helper builds | Four .NET projects, 0 warnings, 0 errors each |
| Repository | 302 passed, 10 explicit opt-in skips |
| Static/contracts | Ruff passed; strict mypy passed across 164 source files; schemas fresh; compileall passed |

Machine-readable limits and results are in
[`p13-attention-crop/acceptance.json`](p13-attention-crop/acceptance.json). P14 is next. No commit,
tag or staging operation was performed.
