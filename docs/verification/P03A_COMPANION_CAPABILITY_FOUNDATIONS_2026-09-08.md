# P03A Companion and Dynamic-Capability Foundations Verification

- Date: 2026-09-08
- Completed: 2026-09-08 13:00:57 +01:00 (Europe/London)
- Model: Gemini 3.8 Flash
- Environment: Windows 11 Pro 10.0.26200 x64, CPython 3.12.10, uv 0.12.10
- Scope: Additive G1A companion architecture contracts, dynamic capability registry/resolver/dispatch, volatile attention buffer & gesture recognition, Kanban desktop object projection, social privacy boundaries, direct dialogue protocol & runtime companion UX.
- Live external providers, Unity overlay, OS UIA hooks, live speech/VLM, and live NekoVerse networking: deliberately not exercised (deferred to subsequent phases P08–P15).

## Behavior implemented

- **Dynamic Capability System (`sora.capabilities`)**:
  - `CapabilityRegistry` storing capability descriptors across multiple categories (`TOOL`, `MEDIA`, `DESKTOP_OBJECT`, `EXTENSION`, `SOCIAL`).
  - `CapabilityResolver` with budget-constrained relevance scoring and strict scope containment (`LOCAL_OWNER`, `LOCAL_RESTRICTED`, `NETWORK_PUBLIC`, rejecting `REMOTE_GUEST`).
  - `dispatch_capability` enforcing active set membership, grant presence, and TTL expiration with typed `CapabilityDeniedError`.
- **Context Compiler Extension (`sora.context.compiler`)**:
  - Scoped context compilation with `privacy_scope="network_public"` filtering, excluding non-public items with auditable manifest reasons (`privacy_scope_excluded`).
  - Active capability rendering in context header under `[ACTIVE_CAPABILITIES]` block.
- **Attention & Gestures (`sora.attention`)**:
  - `CursorRingBuffer`: volatile, in-memory, bounded ring buffer of timestamped cursor samples, validating timezone-aware timestamps and rejecting naive datetimes.
  - Timestamp-based sample lookup with configurable tolerance, and recent sample retrieval.
  - `detect_hover`: centroid calculation for dwell periods >= min_duration within distance thresholds.
  - `recognize_circle`: closed-loop circling gesture recognition returning bounding boxes, filtering linear or undersized inputs.
- **Desktop Objects (`sora.desktop_objects`)**:
  - `KanbanBoardProjection`: deterministic projection from canonical `TaskRecord` collections onto Kanban columns (`TODO`, `DOING`, `DONE`) with specialist assignment and attention flags.
- **Social Boundary & Privacy (`sora.social`)**:
  - `project_public_profile`: isolated projection of public identity (`NetworkProfileProjection`) without leaking system files or internal state.
  - `ingest_social_event`: converts external social events into untrusted observation items (`ContextSource.MEMORY`), never authoritative facts.
  - `validate_outbound_social_payload`: verifies outbound payloads against private sentinels and credentials with case-insensitive rejection.
- **Dialogue & Runtime Layer (`sora.providers.dialogue`, `sora.runtime.service`)**:
  - `DialogueProvider` protocol and `DeterministicDialogueProvider`.
  - Direct `runtime.dialogue()` and `runtime.stream_dialogue()` operating concurrently while background tasks are reasoning.
  - `runtime.dialogue_status()` returning independent availability.
  - `runtime.active_specialists()` inspecting active reasoning runs.
  - `runtime.present_result()` computing adaptive `ResultPresentation` modes (`SILENT`, `BRIEF`, `EXPLAIN`, `WALKTHROUGH`) without exposing private scratchpads.
- **Contracts (`sora.contracts`)**:
  - Added 10 public contract models: `CapabilityDescriptor`, `CapabilityIndexEntry`, `CapabilityIndex`, `CapabilityResolutionRequest`, `ActiveCapabilityManifestEntry`, `ActiveCapabilitySet`, `ResultPresentation`, `AttentionTarget`, `DesktopObjectRecord`, `SocialEventRecord`, `NetworkProfileProjection`, and `ExtensionRegistration`.
  - JSON schemas exported and verified fresh via `python scripts/export-contracts.py --check`.

## Repository verification

```text
.\scripts\verify.ps1
```

Final result:
- Locked dependency synchronization: passed (18 packages).
- Ruff check: passed across `src`, `tests`, and `scripts/export-contracts.py`.
- Strict mypy: passed across 74 source files with zero errors.
- Schema freshness (`python scripts/export-contracts.py --check`): passed for all 22 public contract schemas.
- Pytest: **106 passed in 5.82s** across 19 test modules.
- Python compileall: passed without warnings or errors.

P03A-specific tests prove:
- `tests/capabilities/test_capabilities.py`: scope containment, budget enforcement, contextual scoring, dynamic schema generation, grant checks, and TTL expiration (9 tests).
- `tests/runtime/test_companion_ux.py`: dialogue availability and streaming during active background reasoning, active specialist reporting, steering trace recording, and adaptive presentation mode selection (3 tests).
- `tests/attention/test_attention_objects.py`: ring buffer bounds and sample lookups, hover and circle gesture recognition, AttentionTarget contract validation, and Kanban task projections (6 tests).
- `tests/social/test_social_privacy.py`: network_public context exclusion, public profile projection, untrusted social event labeling, and outbound payload sentinel validation (4 tests).

## Limits retained

- Scope is strictly additive architecture, domain contracts, and deterministic fixtures.
- Hardware/vendor integration (Unity transparent overlay, Win32/UIA OS hooks, audio/TTS pipeline, live NekoVerse networking) is out-of-scope for P03A and belongs to P08–P15.
- Hermes now manages its trusted native tools directly; P03A still does not claim that Core grants
  narrow those tools or that a Hermes workspace is an operating-system sandbox.
- P03A.7 live dialogue acceptance remains a separate follow-on requirement when live provider credentials/models are configured.
