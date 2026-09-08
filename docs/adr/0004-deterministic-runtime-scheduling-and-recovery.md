# ADR 0004: Deterministic runtime scheduling and recovery

- Status: accepted
- Date: 2026-09-07

## Context

P02 established canonical SQLite state, but it did not execute tasks. The first usable text core
needs to keep dialogue responsive while reasoning runs, persist intent before provider launch,
bound concurrency and retries, distinguish task identity from execution attempts, reconcile process
crashes, retain late cancellation results safely, and report only grounded terminal outcomes.

## Decision

Use an `asyncio` application service with a bounded FIFO queue and configurable worker count. Admit a
new task and its first run, originating message, deterministic acknowledgement, revision, events,
and outbox records in one SQLite transaction. The submission idempotency key returns that exact
task, current run, and original acknowledgement on replay. Active-task capacity is checked in the
same transaction so overload cannot leave a partial submission.

Persist a run lease and deadline before calling a provider. The initial runtime is explicitly a
single-process design: on process startup, every persisted lease belongs to a previous process and
is reconciled to `interrupted`, even when its nominal expiry is still in the future. SORA does not
automatically relaunch an interrupted or uncertain attempt. An explicit retry creates a new,
bounded attempt and preserves all earlier run evidence.

Use the versioned provider protocol from P01. The hermetic deterministic provider declares its
capabilities and can inject delay, failure, rate limiting, malformed output, disconnect,
cancellation races, uncertain launch, and unavailability. Unsupported steering returns a typed
error. Cancellation is a state transition distinct from provider confirmation. A late result is
stored as evidence but its patch is not applied after cancellation.

Accept normalized results before applying their proposed patches. Ground reports in persisted task
and result state; pending, failed, unavailable, and cancelled work cannot be worded as successful.
Emit structured trace records for submission, context compilation, launch, result acceptance,
patch disposition, retry/steering, and final latency. Trace fields contain IDs and a context
selection manifest rather than message content and pass through secret redaction.

Deliver durable outbox events at least once. Mark an event delivered only after its consumer
returns successfully; consumers remain responsible for deduplication by event ID. The P03 CLI and
its asynchronous deterministic dialogue stream call the same application service as future APIs.

## Consequences

- Dialogue and inspection remain responsive while bounded background workers reason.
- A caller waiting for terminal completion also observes completed final tracing and lease cleanup.
- Restart does not replay an uncertain external effect or retain a lease from a dead process.
- Explicit retry history is inspectable and capped; retries never create a second user task.
- SQLite serialization favors correctness and modest local workloads over high throughput.
- The current single-process assumption must be replaced by process ownership/fencing before
  multiple Core processes can safely share one database.
- The deterministic provider proves Core behavior, not any live model, network, session, or token
  streaming capability.

## Reversal

A later scheduler, broker, or multi-process lease service may replace the in-process queue if it
preserves atomic admission, stable task identity, immutable attempt history, bounded concurrency,
deadline/cancellation semantics, startup fencing, result/patch separation, truthful reporting,
correlated traces, and at-least-once outbox delivery. Provider adapters and clients must continue to
depend on the versioned contracts rather than scheduler internals.
