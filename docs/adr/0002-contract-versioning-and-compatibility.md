# ADR 0002: Contract versioning and compatibility boundary

- Status: accepted
- Date: 2026-09-07

## Context

SORA Core must coordinate durable state, replaceable providers, reconnecting clients, and eventually
Windows and Unity processes. Native provider objects or permissive unversioned dictionaries would
make replay, migration, validation, and security behavior dependent on whichever backend happened to
produce them.

## Decision

Public records and envelopes begin at schema version `1.0`. The authoritative Python models are
immutable, reject unknown fields, require offset-aware timestamps, constrain identifiers and sizes,
and generate committed JSON Schemas. Core, provider adapters, and clients validate the same JSON
payloads at their boundaries.

Task, agent run, and agent session remain separate. Results, proposed patches, patch application, and
workspace integration have separate identities and outcomes. Task/run/approval transitions use
explicit matrices. Optional provider methods report typed unsupported errors. Events use per-stream
monotonic sequence plus event-ID deduplication.

Capability checks occur outside models and use only typed, persisted grants scoped to owner, device,
project, operation, resource, time, and use limit. Untrusted content is data and cannot grant
authority. Audit output passes through structured redaction before logging.

## Compatibility policy

Compatible additive changes must remain optional and receive fixtures for old and new payloads.
Removing fields, adding required fields, changing types/enums/meaning, or weakening validation
requires a new version and an explicit translator/migration. Unknown versions and extra fields fail
closed. Backend-specific fields are translated into normalized fields or retained only in scoped
artifacts; they do not leak into shared contracts.

## Consequences

- Contract failures are early and inspectable instead of becoming provider-specific branches.
- Replays and reconnects have deterministic duplicate/order semantics.
- Strictness creates deliberate versioning work when interfaces evolve.
- P02 persistence can build migrations/outbox behavior against stable v1 envelopes.

## Reversal

The serialization technology can change if it preserves the published JSON behavior and supplies a
versioned translator. Loosening validation or admitting backend-native objects would require a new
ADR and security/compatibility evidence.

