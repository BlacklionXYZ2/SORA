# ADR 0001: SORA naming and legacy prototype migration

- Status: accepted
- Date: 2026-09-07

## Context

The discovered prototype uses the product/package name `ava`, an `ava` console command, `AVA_*`
environment variables, an `ava.db` database, and identity text that names Ava. The project owner has
settled on SORA as the actual product and agent name. Existing identifiers may already be referenced
by user data or local configuration.

## Decision

All new packages, entry points, environment variables, schemas, documentation, and product text use
SORA. The P00 scaffold therefore exposes `python -m sora` and the `sora` console script.

Legacy identifiers are not renamed in place. The prototype and its private state are preserved as a
hashed recovery archive. P01 will specify compatibility contracts; P02 will own a versioned,
transactional importer that reads legacy identifiers explicitly and records source-to-destination
mapping. Any temporary `ava` alias must be deliberate, tested, and documented as deprecated.

## Consequences

- New work has one canonical name and avoids expanding the placeholder namespace.
- Existing state remains recoverable and byte-preserved before migration.
- The initial SORA scaffold does not claim to read the old database.
- Migration completion is deferred until its target schemas, validation, rollback, and count checks
  exist.

## Reversal

The decision can be revised before stable public interfaces exist. The legacy archive and mapping
requirements remain valid regardless of the eventual display name.

