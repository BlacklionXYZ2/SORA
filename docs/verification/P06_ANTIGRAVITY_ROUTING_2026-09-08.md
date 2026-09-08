# P06 Antigravity and Rule-Based Routing Verification

- Date: 2026-09-08
- Implementation completed: 2026-09-08 13:55:00 +01:00 (Europe/London)
- Dependency closure / combined acceptance: 2026-09-08 15:17:15 +01:00 (Europe/London)
- Models: Gemini 3.8 Flash (P06 implementation); GPT-5.6 Sol (P05 integration and dependency closure)
- Environment: Windows 11 Pro 10.0.26200 x64, CPython 3.12.10, uv 0.12.10, agy 1.1.27 (`C:\Users\oscar\AppData\Local\agy\bin\agy.exe`)
- Scope: Non-interactive Antigravity CLI adapter, deterministic rule-based routing engine, dialogue/status fast-paths, explicit override protection (no silent substitution), privacy scope containment, bounded automatic fallback, conversational steering disambiguation, proportional adaptive presentation, and multi-provider runtime wiring.

## P05 dependency closure

> [!IMPORTANT]
> **Satisfied 2026-09-08 15:17:15 +01:00.**
>
> P05 now allocates a manager-owned worktree for each configured coding write, binds Codex to the
> same lease and workspace reference, persists a complete review artifact, and releases the lease.
> Coding writes have no provider fallback and unconfigured writes fail before submission. A live
> P06-routed GPT-5.6 Luna run on the full SORA repository passed this boundary. This closure is GPT-5.6
> Sol integration evidence and does not change Gemini 3.8 Flash's P06 implementation attribution.

## Behavior Implemented

- **Antigravity CLI Adapter (`sora.providers.antigravity`)**:
  - Wrapped `agy.exe` non-interactive CLI invocation with flags: `--output-format json`, `--effort <low|medium|high>`, `--print="..."`.
  - Native session persistence: extracted `conversation_id` from JSON payload and provided `--conversation <id> --continue` for session resumption.
  - Process lifecycle & safety: child process termination on cancellation or timeout, process lookup exception handling, and response byte ceilings (`max_output_bytes`).
  - Result normalization: parsing structured JSON responses or fallback raw text into `NormalizedResult`, rejecting malformed envelopes with typed `ProviderResultError`.
- **Deterministic Routing Engine (`sora.routing.router`)**:
  - Fast-paths: `dialogue_fast_path` and `status_lookup_fast_path` to bypass worker queues for instant companion responses.
  - Intent classification: classified prompt text and metadata into `research`, `coding_read`, `coding_write`, `deterministic_offline`, or `reasoning_general`.
  - Isolated coding writes select Codex with an empty fallback list; requests that cannot be isolated remain `p05_deferred` and are rejected before task creation.
  - Explicit manual override protection: explicit user requests for a specific backend are strictly honored without silent substitution. If the backend is unavailable, `ProviderLaunchError(UNAVAILABLE)` is raised with an empty fallback sequence.
  - Privacy scope containment: local-only context filters out cloud providers and rejects explicit cloud requests.
  - Conversational steering disambiguation (`disambiguate_steering`): maps "Cody", "Hermes", "Antigravity"/"AG", or pronouns to active runs when unambiguous, returning `None` if ambiguous.
- **Runtime Multi-Provider Integration (`sora.runtime.service`)**:
  - Multi-provider registry (`self.providers`) supporting dynamic registration and capability discovery.
  - Trace recording: emits `phase="routing.selected"` on task submission and `phase="routing.fallback"` on bounded automatic fallback.
  - Conversational steering (`runtime.steer_from_conversation`): applies steering instructions only to targeted active runs.
  - Proportional adaptive presentation (`runtime.present_result`): dynamically selects `BRIEF`, `EXPLAIN`, or `WALKTHROUGH` presentation modes with specialist attribution.
  - Managed P05 handoff: configured writes allocate a per-run worktree from an explicit base, bind the concrete Codex provider, capture a durable review artifact before result acceptance, and release the lease in terminal cleanup.
- **CLI Flags (`sora.__main__`)**:
  - Added `--provider antigravity` and options: `--antigravity-command`, `--antigravity-cwd`, `--antigravity-model`, `--antigravity-effort`.

## Verification Results

```text
.\scripts\verify.ps1
```

Final verification output:
- **Pytest**: **135 passed in 7.67s** across 22 test modules (29 new tests added).
  - `tests/providers/test_antigravity.py` (11 tests): JSON parsing, text fallback, malformed errors, capabilities, non-interactive execution, session ID extraction, session resumption, timeout handling, cancellation.
  - `tests/routing/test_routing.py` (11 tests): dialogue/lookup fast-paths, intent-based routing, P05.3 write holding, explicit overrides, no silent substitution, privacy containment, conversational steering disambiguation.
  - `tests/runtime/test_multi_provider_routing.py` (7 tests): multi-provider auto routing, event traces, explicit override enforcement, bounded auto fallback, no fallback on explicit failure, conversational steering, adaptive presentation modes.
- **Strict mypy**: passed across 80 source files with zero errors.
- **Ruff check**: passed across `src`, `tests`, and `scripts/`.
- **Python compileall**: passed without warnings or errors.
- **Schema freshness**: passed for all 22 public contract schemas.
- **Regression test**: all existing P00–P04 and P03A tests passed without regression.

Final combined P05/P06 verification on the integrated tree:

- **Pytest**: **145 passed in 9.08s** across 24 test modules.
- **Strict mypy**: passed across 85 source files; Ruff and compile checks passed.
- **Fresh package**: sdist/wheel build and isolated-wheel imports for both providers, routing,
  runtime, and workspaces passed.
- **Live managed route**: task `task-44bf8027-4fc8-4581-a32e-7f96be73fd79` selected Codex with no
  fallback, used clean base `f370082b89924da37b832fec59b78e1ab4b9b52c`, retained exactly two
  requested file edits in its worktree, persisted the review artifact, and left no lease or source
  checkout change. Host verification against the exact worktree passed all 6 Codex provider tests.

## Limits Retained

- Coding writes still require explicit repository/workspace/base configuration; without it they fail closed.
- The managed artifact is reviewable but deliberately not auto-merged, staged, or committed.
- Antigravity adapter exercises non-interactive JSON mode; live streaming events remain unsupported until native streaming protocols are exposed.
