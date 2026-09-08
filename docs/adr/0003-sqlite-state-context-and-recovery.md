# ADR 0003: SQLite state, scoped context, and recovery

- Status: accepted
- Date: 2026-09-07

## Context

P01 established strict model-independent contracts. SORA now needs durable canonical state that can
survive restarts, reject stale writes, emit reconnectable events, keep identity independent from
providers, compile bounded private context, and restore without copying secrets accidentally.

## Decision

Use SQLite with foreign keys, WAL mode, a bounded asynchronous write lock, short `BEGIN IMMEDIATE`
transactions, and ordered schema migrations. No transaction performs model, network, UI, approval,
or other external waits. Canonical mutations advance a global observation revision and insert their
durable event plus outbox row in the same transaction.

Entity versions, patch idempotency keys, and source task/run scope determine patch safety. A stale
global base revision does not reject an independent append. A mismatched entity precondition records
a conflict without applying operations. Result artifacts are accepted separately from patch
application. Failed transactions roll back state, revision, event, and outbox together.

Identity revisions load all five required Markdown files, hash their deterministic content, and do
not contain a provider field. Memories retain provenance, evidence, scope, sensitivity, retention,
validity, correction, and deletion state. Superseded, expired, and deleted records remain inspectable
when explicitly requested.

Context compilation uses an explicit owner/project boundary, source labels, deterministic priority,
secret/expiry exclusion, and a recorded selection manifest. Identity and exact constraints are
mandatory; compilation fails instead of silently truncating them. The current character budget is a
deterministic provisional bound, to be supplemented by measured tokenizer budgets in P03.

Backups use SQLite's consistent backup API, copy hashed non-secret artifacts, and produce a manifest.
Restore only targets a new or empty directory, rejects hash failures and traversal paths, and never
copies directories named `secrets`.

## Consequences

- P03 can build scheduling and CLI behavior on restart-safe repositories and events.
- At-least-once delivery can be implemented from the durable outbox without coupling clients to
  write transactions.
- Serialized writes favor correctness for the initial single-owner process; concurrency budgets must
  be measured later.
- Secret configuration needs its own protected backup mechanism; omission is intentional and
  visible in the manifest.

## Reversal

Another database or context representation may replace these internals if it migrates every schema
version and preserves contract validation, entity preconditions, result/patch separation, atomic
outbox behavior, scope exclusions, and verified backup/restore semantics.

