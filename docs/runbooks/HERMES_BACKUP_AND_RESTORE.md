# Hermes prototype backup and restore

The legacy prototype is currently located at
`C:\Users\oscar\Desktop\agent-workspace\Hermes`. Its `data\ava.db` and identity files may contain
private user state. They must remain outside versioned source.

## Create a backup

From the SORA repository:

```powershell
.\scripts\backup-hermes.ps1
```

The script creates a timestamped ZIP, SHA-256 sidecar, and metadata-only manifest under
`.local\backups\`. The ignored archive includes the legacy database, identity files, source, tests,
and project metadata. It excludes caches, virtual environments, `.env`, and Git internals.

To use another source or destination, pass explicit absolute paths:

```powershell
.\scripts\backup-hermes.ps1 -SourceRoot C:\path\to\Hermes -DestinationRoot D:\private-backups\SORA
```

## Verify and restore

1. Compare the ZIP hash with its `.sha256` sidecar using `Get-FileHash -Algorithm SHA256`.
2. Extract into a new, empty directory. Do not extract over either the legacy prototype or SORA.
3. Open the restored `data\ava.db` read-only and run `PRAGMA quick_check` before any migration.
4. Run the restored prototype tests from a fresh environment.
5. Keep the original and backup unchanged until a separately tested importer has migrated all
   supported records and produced source-to-destination counts and identifiers.

This is a recovery backup, not a SORA database migration. P02 will implement versioned SORA
migrations and a tested importer. Until then, `ava`, `AVA_*`, the `ava` console command, and existing
database identifiers remain legacy compatibility inputs; new code and product text use `sora` and
`SORA_*`.

