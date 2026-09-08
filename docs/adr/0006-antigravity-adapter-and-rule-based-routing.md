# ADR 0006: Antigravity adapter and rule-based routing

- Status: accepted
- Date: 2026-09-08
- Verified amendment: 2026-09-08

## Context

SORA requires multi-agent capabilities across specialized backends: Hermes (deep reasoning, planning), Codex (code editing, repository tasks), Antigravity (research, multi-turn tool orchestration), and deterministic mock (offline, tests). P04 proved the Hermes ACP adapter, while P06 requires an adapter for the Google Antigravity CLI (`agy.exe`) and a deterministic routing engine to arbitrate tasks, preserve privacy boundaries, prevent silent degradation, and support conversational steering and proportional presentation.

At initial implementation, Phase P05 workspace isolation had not yet been finalized, so P06 held coding writes as deferred. P05 completed on 2026-09-08 at 15:17:15 +01:00 and now provides the managed worktree boundary used by routed Codex writes.

## Decision

1. **Antigravity CLI Adapter (`AntigravityProvider`)**:
   - Wrap the non-interactive Google Antigravity CLI (`agy.exe`) via `asyncio.create_subprocess_exec`.
   - Command line flags: `--output-format json`, `--effort <low|medium|high>`, `--print="..."`.
   - Session continuity: capture the native conversation ID emitted in JSON output and pass `--conversation <id> --continue` for session resumption.
   - Resource governance: enforce per-request timeout, terminate child processes upon cancellation/timeout, and enforce maximum response output limits (`max_output_bytes`).
   - Conformance: normalize structured JSON or parse text fallback into `NormalizedResult`, rejecting malformed envelopes with typed `ProviderResultError`.

2. **Deterministic Routing Engine (`RoutingEngine`)**:
   - Fast paths: evaluate `dialogue_fast_path` and `status_lookup_fast_path` synchronously to bypass heavyweight reasoning queues.
   - Intent classification: classify task prompts and tags into `research`, `coding_read`, `coding_write`, `deterministic_offline`, or `reasoning_general`.
   - Explicit override protection: if a specific backend is requested, do not silently substitute it with a fallback backend. If the requested provider is unavailable, raise `ProviderLaunchError(UNAVAILABLE)` with an empty fallback sequence.
   - Privacy scope containment: if the task context contains local-only / sensitive data, filter out cloud providers and reject explicit cloud requests.
   - P05 safety boundary: when isolation is configured, route coding writes to Codex with no fallback; otherwise mark the decision `p05_deferred=True` and reject it before creating a task.
   - Conversational steering disambiguation: resolve natural references ("Cody", "Hermes", "Antigravity", "AG", or pronouns) to the target task run only when disambiguation is unambiguous; reject or ignore ambiguous references.

3. **Runtime Integration (`SoraRuntime`)**:
   - Multi-provider registry (`self.providers`) initialized with capability probing during `start()`.
   - Task submission records `phase="routing.selected"` in the runtime event trace.
   - Bounded automatic fallback records `phase="routing.fallback"` and updates the task run's actual provider.
   - Dynamic presentation (`present_result`): map outcome attributes to `ResultPresentation` modes (`SILENT`, `BRIEF`, `EXPLAIN`, `WALKTHROUGH`) with specialist identities.
   - Managed coding handoff: allocate one explicit-base worktree per coding run, bind the Codex provider and request to the same workspace/lease, capture the review artifact, then release the lease on every terminal path.

## Consequences

- SORA runtime can dynamically route tasks across multiple specialist providers based on intent, privacy, and active capabilities.
- Explicit user backend selections are strictly enforced with zero silent substitution.
- Dialogue and status lookups remain immediate and never stall waiting for worker queues.
- P05 dependency is satisfied: configured coding writes execute only in owned Codex worktrees and unconfigured writes remain deferred/fail closed.
- Comprehensive test coverage verifies routing logic, override protection, bounded fallback, and adapter conformance under both mock and CLI environments.

## Reversal

The routing engine and Antigravity adapter adhere strictly to public contracts (`ReasoningProvider`, `ProviderRequest`, `NormalizedResult`, `RoutingDecision`). The routing strategy or CLI invocation flags can be swapped or refactored without breaking downstream runtime consumers.
