# ADR 0012: Portable Windows Release and Versioned State Slots

- Status: accepted; P15.3 complete
- Date: 2026-09-22
- Completed: 2026-09-22 15:57:48 +01:00
- Model: GPT-5.6 Sol

## Context

SORA previously ran from its source checkout and had independently verified Core, Windows helper and
Unity builds. That did not establish a clean-profile install, a coherent artifact, safe application
updates, database rollback, optional startup or an explicit personal-data lifecycle. Updating an
active SQLite database in place would make application rollback unsafe once a forward-only migration
had run.

## Decision

1. A release is a portable, per-user Windows bundle containing CPython 3.12.10, locked Core
   dependencies/wheel, self-contained .NET helpers, the verified Unity player, identity/PWA assets,
   attribution and operator documentation. No host Python, .NET or Unity installation is required at
   runtime.
2. Every shipped file is listed with its byte count and SHA-256 in `release-manifest.json`.
   Installation/update reject links, reparse points, path escapes, duplicate/missing/unexpected files
   and byte changes. Maintenance commands use Python `-B` so verification cannot rewrite extracted
   bytecode before hashing it.
3. Replaceable application versions live under `app/versions/<release-id>`. Personal canonical state
   lives separately under `state/slots/<state-id>`. One atomic `current.json` names the active pair.
4. Update never migrates the active database. It creates a hashed online backup, restores a new slot,
   lets the new bundled runtime apply ordered migrations, requires SQLite quick/foreign-key checks,
   and only then switches the pointer. Failed update retains the old pointer. Rollback selects the
   previous application/state pair instead of applying a reverse migration.
5. Uninstall removes application files and the exact managed startup entry while retaining state by
   default. An explicit purge is allowed only when exact install/state markers match the requested
   roots. Reinstall clones the last retained slot into a new verified slot.
6. Startup is an explicit per-user Startup-folder entry with paths and a token-file location, never a
   credential. The installer creates no service, scheduled task, firewall rule, public listener or
   administrator-level configuration.
7. Core database and registered artifacts participate in backup. Credentials, API tokens, TLS keys,
   external provider state, model caches, arbitrary user files and coding worktrees do not. Voice
   models remain separately provisioned against P14's pinned digests/licences; user avatars remain
   subject to their own redistribution terms.

## Consequences

- Release archives are comparatively large because each Windows helper is self-contained and the
  Unity player is included. The verified ZIP is about 322 MiB; smaller shared-runtime packaging may
  be evaluated later without weakening clean-profile operation.
- Application and state history consume additional disk until the operator deliberately removes old
  rollback slots/backups.
- The current archive is unsigned. Its exact SHA-256 and per-file manifest provide integrity evidence
  for this acceptance artifact, not publisher identity or an automatic-update trust chain.
- External provider CLIs and optional voice models remain independent installations and must be
  configured explicitly.

## Reversal

The portable bundle can be replaced by a future signed installer or package manager while preserving
the same manifest, separate state root, staged migration and paired rollback semantics. The default
uninstall leaves state available for migration to that future format.
