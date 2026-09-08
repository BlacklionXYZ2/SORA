# P02 persistence, context, and recovery verification

- Date: 2026-09-07
- Model: GPT-5.6 Sol
- Environment: Windows 10.0.26200 x64, CPython 3.12.10, uv 0.12.10
- Scope: hermetic SQLite, identity, memory, patch, context, outbox, backup, and restore behavior
- Live providers, HTTP/WebSocket delivery, hardware, and personal data import: not exercised

## Behavior implemented

- Ordered SQLite migrations through schema version 2, foreign keys, WAL, busy timeout, serialized
  asynchronous writes, and explicit rollback.
- Canonical owners, projects, conversations, finalized messages, tasks, agent runs, agent sessions,
  identity revisions, facts, memories, normalized results, patches, events, outbox rows, artifacts,
  approvals, and grants.
- Atomic revision/event/outbox creation for canonical mutations.
- Separate normalized-result acceptance and proposed-patch application.
- Patch source owner/project validation, idempotent replay, entity-version conflict recording, stale
  independent append support, and transaction rollback after a partially attempted patch.
- All five SORA identity files, deterministic identity hashes, active revision switching, and
  provider-independent restore.
- Memory provenance/evidence/scope/sensitivity/retention/validity fields plus correction,
  supersession, expiry, soft deletion, and active-versus-historical inspection.
- Deterministic bounded context with exact constraints, explicit source/epistemic labels,
  owner/project/secret/expiry exclusions, priority, and a redacted selection manifest.
- Consistent SQLite plus artifact backup, SHA-256 manifest, secret-directory exclusion, clean
  restore, traversal rejection, and forward migration after restore.

## Verification

```text
.\scripts\verify.ps1
```

Final stage result:

- Locked dependency synchronization: passed with 18 packages.
- Ruff: passed.
- Strict mypy: passed across 45 Python source/test/script files.
- Generated P01 schema freshness: passed.
- Pytest: 49 tests passed.
- Compileall: passed.

An sdist and wheel were built and installed into a fresh Python 3.12 environment. The installed
wheel initialized schema version 2 and its new database returned `PRAGMA quick_check=ok`.

P02-specific tests prove:

- a schema-v1 fixture migrates to v2 and gains the pending-outbox index/column;
- restart preserves representative history, task, run, session, approval, grant, events, and outbox;
- failed patch transactions leave counts, revision, facts, events, and outbox unchanged;
- a normalized result remains stored when its state patch conflicts;
- duplicate patch replay creates no repeated fact or event;
- an append with an old global base revision succeeds when it has no conflicting entity precondition;
- patch facts inherit the source task's project and mismatched owner/project scope is denied;
- identity loads all five files and remains identical after reopening the database;
- expired, superseded, and deleted memories remain labeled while active retrieval excludes them;
- the golden context fixture retains exact constraints and FACT/INFERENCE labels while excluding a
  different project's private memory;
- oversized low-priority context is excluded with a manifest reason, and mandatory content that
  cannot fit raises an explicit error;
- clean backup/restore retrieves task, history, identity, and artifact content while excluding the
  secret fixture;
- a malicious `../` manifest entry is rejected before restore.

## Limits

The outbox is durable but has no dispatcher yet; P03/P08 will implement bounded delivery and replay.
Repositories do not wait on providers and do not yet implement the scheduler, leases, cancellation
reconciliation, or CLI. Character counts are the current deterministic context bound; provider-
specific token measurement comes with the runtime. Legacy Ava database import remains deliberately
unimplemented until a reviewed source-to-v2 mapping is added. Secret backup remains separate by
design.
