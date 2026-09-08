# SORA backup and restore

P02 provides the library operations `sora.persistence.backup.create_backup` and `restore_backup`.
An operator-facing CLI will be added with the text runtime rather than exposing an unreviewed command
surface now.

## Backup contents

A backup directory contains:

- `data/sora.db`, created through SQLite's online backup API;
- hashed files copied from the configured artifact root;
- `manifest.json`, containing schema version, timestamp, file paths, sizes, SHA-256 values, and
  explicit exclusions.

Any artifact path containing a directory component named `secrets` is excluded. Credentials and
secret configuration require a separate protected recovery process; they are never silently bundled.

## Restore rules

Restore accepts only a missing or empty destination. Before copying, it verifies every manifest path
is relative and contains no `..` component, and verifies every file's SHA-256. It never overwrites an
existing installation. After restore, initialize the database normally to apply any newer ordered
migrations, then run SQLite `PRAGMA quick_check` and application verification before switching the
active data path.

The integration test in `tests/persistence/test_identity_memory_backup.py` creates canonical task,
history, identity, and artifact data; backs it up; restores it into a clean directory; and verifies
representative records and artifact content. It separately verifies secret exclusion and traversal
rejection.

