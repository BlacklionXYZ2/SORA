# ADR 0008: Parallel Workspaces, Synthesis, and Review Workflow

- Status: accepted; P07 complete
- Date: 2026-09-08
- Completed: 2026-09-08 16:15:00 +01:00
- Model: Gemini 3.8 Flash

## Context

P05 established isolated, manager-owned git worktrees for single-writer coding tasks, preventing concurrent corruption of the primary repository checkout. P06 established multi-provider routing and fallback across Hermes, Codex, and Antigravity. However, multi-agent collaboration, competitive solution exploration, and parallel specialist work remained constrained:
1. Workspace lifecycle was incomplete: worktree allocation existed, but lacked active tracking, diffing, inter-workspace comparison, crash recovery, dirty-state discard protection, and safe TTL-based cleanup.
2. Parallel execution lacked structured synthesis: executing multiple candidate providers required isolated budgets and worktrees, deterministic comparison of outputs, transparent exposure of disagreements or failures, and strict guardrails preventing automatic execution of untrusted candidate instructions or synthetic consensus fabrication.
3. Review and integration lacked safety gates: integrating candidate changes into the target branch required conflict detection against moving base revisions, pre-integration validation commands, non-empty explicit human authorization (`authorized_by`), preservation of untracked checkout files during patch application, and reversible rollback.

## Decision

### 1. Workspace Lifecycle Management (`sora.workspaces.git`)
- Introduce explicit `WorkspaceStatus` lifecycle states: `ACTIVE`, `RELEASED`, `RECOVERED`, `DISCARDED`.
- Require exclusive, non-shared write leases (`WorkspaceLease`). A second writer cannot acquire or renew a lease owned by another worker.
- Provide `diff_workspace()` and `diff_between_workspaces()` for inspecting git changes without modifying worktree state.
- Implement zero-data-loss crash recovery via `recover_workspace()`: if a worker crashes or abandons a lease with uncommitted modifications, SORA snapshots diffs, untracked files, and recovery artifacts to durable disk storage before unlinking the lease and marking status `RECOVERED`.
- Enforce resolved-path containment and dirty protection on `discard()`: worktree paths outside the configured workspace root are strictly rejected (`WorkspacePathEscapeError`), and discarding dirty worktrees without `force=True` is prohibited (`WorkspaceDirtyDiscardError`). When `force=True` is supplied, an automatic recovery snapshot is captured to prevent accidental data loss.
- Provide `cleanup_expired()` to safely release or recover expired leases based on whether dirty modifications exist.

### 2. Deterministic Bounded Fan-Out & Multi-Candidate Synthesis (`sora.workspaces.synthesis`)
- Concurrently execute candidate reasoning providers across isolated branch runs and dedicated worktrees via `run_fanout()`.
- Implement `SynthesisEngine`:
  - Deterministically evaluates candidate outputs without inventing synthetic consensus.
  - Classifies consensus into `FULL_AGREEMENT`, `PARTIAL_AGREEMENT`, `DISAGREEMENT`, `PARTIAL_FAILURE`, or `ALL_FAILED`.
  - Transparently surfaces failures, exit codes, and disagreements in diffs or conclusions.
  - Treats candidate conclusions as non-authoritative recommendations: synthesis never executes candidate commands or state mutations directly.

### 3. Gated Review and Atomic Integration (`sora.workspaces.review`)
- Implement `ReviewManager`:
  - `check_conflicts()`: compares worktree branch/diff against current target HEAD to detect merge conflicts before integration.
  - `validate()`: executes pre-integration validation commands (e.g. tests, lint, compilation) within the workspace directory, capturing exit codes and outputs.
  - `integrate()`: enforces explicit human authorization gating (`authorized_by` must be non-empty; raises `IntegrationAuthorizationError`). Ensures target repository is free of conflicts (`IntegrationConflictError`) and uncommitted tracked changes before applying the workspace diff via `git apply --index`. Preserves untracked files in the checkout.
  - `rollback()`: enables reversing an integration by reverting applied commit/patch artifacts, verifying repository integrity, and updating durable integration records.

## Consequences

- Parallel candidate explorations run with strict isolation: distinct run IDs, individual worktrees, and isolated leases.
- Discarding or abandoning workspaces can never silently destroy uncommitted work.
- SORA Core remains strictly authoritative over merging and state application; no reasoning provider or synthesis engine can auto-merge code without explicit operator authorization.
- Full verification of the combined P00–P07 system reaches 163 passing tests, strict mypy across 91 source files, and clean linting.

## Reversal

The workspace manager and review subsystem may be extended or backed by alternative VCS or containerized sandbox systems provided that exclusive leases, path containment, dirty snapshot recovery, conflict detection, explicit merge authorization, and rollback safety invariants are strictly maintained.
