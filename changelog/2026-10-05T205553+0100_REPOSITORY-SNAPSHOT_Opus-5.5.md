# Repository snapshot commit and ignore rules

Model name: **Opus 5.5**. Checkpoint **2026-10-05 20:55:53 +0100**, Europe/London. Status: **committed locally at the
owner's request**; pushing to a private GitHub repository is pending GitHub CLI login.

## Changes

- `.gitignore`: now ignores `*.vrm`, because the owner asked to leave large Unity assets out.
  The Seed-san sample avatar is re-downloadable from its public source, which is linked in the
  file; its licence note and `.meta` remain committed.
- `.gitignore`: now ignores `/dist/`, `/tmp_test/` and `/%SystemDrive%/` explicitly. These
  stray or local-output folders were previously excluded only by accident, through the `*.db`
  rule.
- Commit `55d738a` snapshots all work since the P05 baseline: 978 files (924 added, 53 modified,
  1 renamed, none deleted). The working tree had never been committed since 2026-09-08.

## Verification

- Before committing: candidate files total 18.9 MB. The largest was the 10.4 MB avatar, now
  excluded.
- No credentials are included. The only key material is the TLS test fixtures under
  `tests/fixtures/tls`, which are deliberately committed for tests.
- No excluded path was staged.

## Limits and next

`gh` is not logged in, so the private repository has not been created or pushed yet.
