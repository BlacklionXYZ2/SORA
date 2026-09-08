# ADR 0007: Codex App Server and owned worktrees

- Status: accepted for P05.1–P05.3
- Date: 2026-09-08

## Context

P05 requires a supported Codex interface, durable project/thread identity, cancellation, and an
initial single-writer safety boundary before coding changes. The SORA checkout currently has no Git
commit, so it cannot itself be the base of a Git worktree. Read-only provider acceptance and an
isolated committed fixture can still prove the adapter and allocation mechanics without altering the
user's checkout or inventing a base revision.

## Decision

Use the documented Codex App Server JSON-RPC protocol over stdio. One server process is owned per
SORA run. The adapter initializes the connection, starts or resumes a native thread, starts a turn,
observes completed agent/command/file items, interrupts through `turn/interrupt`, and normalizes the
authoritative final agent message. GPT-5.6 Luna at low effort is the default for bounded cost.

Direct CLI use is read-only. A write run requires `workspace-write`, a durable
`WorkspaceRecord`, the matching `ProviderRequest.workspace_ref`, and a current exclusive lease from
`GitWorkspaceManager`. `danger-full-access` is rejected. The manager allocates a detached worktree
from an explicit resolvable base commit beneath its configured state root, records source dirty
state and ownership before work, and captures base/head/status/files/diff afterward. It never stages,
commits, merges, or deletes a handed-off worktree; broader recovery and cleanup belong to P07.

## Consequences

- Native Codex threads remain backend working context, while SORA retains task/run/result identity.
- Read-only and write authority are mechanically distinct rather than prompt-only promises.
- Worktrees prevent checkout collisions but are not security sandboxes; App Server sandbox policy is
  still required.
- Unexpected command/file approval requests are declined under `approvalPolicy=never`.
- Initial leases are durable files and fail closed for a second writer. Cross-process heartbeat,
  recovery, discard, and cleanup remain P07 work.
- P05 cannot be marked complete until a real full-SORA base commit exists and P05.4 is repeated on
  that base without mutating or committing the user's checkout.

## Reversal

Another supported Codex transport or workspace implementation may replace these components if it
preserves `ReasoningProvider`, native session identity, explicit sandboxing, durable ownership,
review artifacts, and no-automatic-integration behavior.
