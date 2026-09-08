# ADR 0007: Codex App Server and owned worktrees

- Status: accepted; P05 complete
- Date: 2026-09-08
- Completed: 2026-09-08 15:17:15 +01:00

## Context

P05 requires a supported Codex interface, durable project/thread identity, cancellation, and an
initial single-writer safety boundary before coding changes. Early acceptance used an isolated
committed fixture because the SORA checkout did not yet have a base commit. The authorized SORA
baseline now permits full-project acceptance against an explicit immutable base.

## Decision

Use the documented Codex App Server JSON-RPC protocol over stdio. One server process is owned per
SORA run. The adapter initializes the connection, starts or resumes a native thread, starts a turn,
observes completed agent/command/file items, interrupts through `turn/interrupt`, and normalizes the
authoritative final agent message. GPT-5.6 Luna at low effort is the default for bounded cost.

Direct CLI use is read-only. A write run requires `workspace-write`, a durable
`WorkspaceRecord`, the matching `ProviderRequest.workspace_ref`, and a current exclusive lease from
`GitWorkspaceManager`. `danger-full-access` is rejected. The manager allocates a detached worktree
from an explicit resolvable base commit beneath its configured state root, records source dirty
state and ownership before work, and captures base/head/status/files/diff afterward. A
`CodingRunArtifact` joins that Git evidence to provider outcome, command/test activity, files,
warnings, and uncertainties. P06 coding-write routing allocates and binds one workspace per run,
captures the artifact before accepting the result, prohibits toolful fallback, and releases the
lease in terminal cleanup. It never stages, commits, merges, or deletes a handed-off worktree;
broader recovery and cleanup belong to P07.

## Consequences

- Native Codex threads remain backend working context, while SORA retains task/run/result identity.
- Read-only and write authority are mechanically distinct rather than prompt-only promises.
- Worktrees prevent checkout collisions but are not security sandboxes; App Server sandbox policy is
  still required.
- Unexpected command/file approval requests are declined under `approvalPolicy=never`.
- Initial leases are durable files and fail closed for a second writer. Cross-process heartbeat,
  recovery, discard, and cleanup remain P07 work.
- P05 full-SORA acceptance passed from explicit base `f370082`; the source checkout remained clean,
  the review worktree retained only the requested edits, and the lease was released.

## Reversal

Another supported Codex transport or workspace implementation may replace these components if it
preserves `ReasoningProvider`, native session identity, explicit sandboxing, durable ownership,
review artifacts, and no-automatic-integration behavior.
