# P15.3 Windows release operations — GPT-5.6 Sol

Status: **complete 2026-09-22 15:57:48 +01:00**.

## Release artifact

- Release ID: `sora-p15.3-acceptance-20260922-r5`
- Directory: `.local/releases/sora-p15.3-acceptance-20260922-r5`
- ZIP: `.local/releases/sora-p15.3-acceptance-20260922-r5.zip`
- ZIP bytes: **337,358,127**
- ZIP SHA-256: `3e80c413c3ae264bc01e5e7f806b15498e904b016669e69cd8481a79c793bab3`
- Manifested files: **4,644**
- Uncompressed manifested bundle bytes: **793,249,175**
- Runtime: portable CPython **3.12.10**, locked dependencies and SORA wheel
- Unity: fresh Windows x64 player after **55/55** PlayMode tests
- Helpers: self-contained .NET 10 `win-x64` observation, action, type and capture executables

The final ZIP was extracted into a new directory. Its bundled Python 3.12.10, running with bytecode
writes disabled, reverified the exact 4,644-file manifest. This specifically closes an earlier test
failure in which ordinary interpreter startup refreshed timestamp-invalidated `.pyc` after ZIP
extraction. No-bytecode-write mode now applies to bundled verification, install/update/uninstall,
state maintenance and stable application launchers.

## Clean-profile and upgrade acceptance

`scripts/verify-release.ps1` created an isolated Windows profile tree without using its host Python,
.NET runtime or Unity installation for the installed application. It then passed:

1. release hash/file-set verification;
2. per-user clean install and optional isolated Startup-folder entry;
3. portable Core initialization at schema 7 with `quick_check=ok` and zero foreign-key errors;
4. one deterministic sentinel task producing one persisted task and two messages;
5. pre-upgrade online SQLite/artifact backup;
6. restore to a separate state slot;
7. migration and verification by the new bundled runtime;
8. atomic activation with the sentinel preserved;
9. rollback to the prior application/state pair with the sentinel preserved;
10. uninstall with application/startup removed and personal state retained; and
11. reinstall from retained state with a newly cloned slot and the sentinel preserved.

The acceptance profile is
`.local/p15.3-release-acceptance-6b221bf9-067d-4f92-9c6f-da4f4bd56031`; its machine-readable result is
also copied into versioned evidence. This is a clean isolated profile-path test on the reference
Windows account, not creation of a separate OS user or administrator-level installer test. The bundle
itself has no runtime dependency on software installed in that account.

All four packaged helpers were executed with empty input and independently returned a bounded
`invalid_request` JSON response with exit code zero. This proves their packaged entrypoints load; the
earlier native phase evidence remains the proof of real UIA/capture behavior.

## Safety properties

- Manifest creation/verification rejects tampering, unexpected files, path escape and unsafe links.
- Windows transient antivirus/indexer rename handles receive a bounded retry; failure cannot write
  the active pointer.
- Update writes `current.json` only after backup, restore, migration and integrity checks pass.
- A deterministic forced migration failure leaves `current.json` byte-identical.
- Rollback uses the old unmodified state slot instead of downgrading the migrated slot.
- Uninstall retains personal state unless purge is explicit.
- Purge requires marker paths to resolve exactly to the requested install/state roots.
- Reinstall clones retained state rather than mutating it in place.
- Optional startup contains no token and touches no real Startup folder during acceptance.

## Personal data and asset boundary

The installed application and state use separate roots. Backups include the canonical SQLite
database and registered `.local/artifacts`, excluding any artifact `secrets` directory. Credentials,
API tokens, TLS private keys, provider configuration, local model caches, coding worktrees and
arbitrary user files are not silently packaged or backed up. Default uninstall retains state.

The SORA identity and PWA are bundled. A normal release includes the Unity player, Seed-san VRM and
attribution. Silero VAD, faster-whisper and Kokoro models remain external and are governed by P14's
recorded versions, licences and digests. The artifact is unsigned; no publisher-signing or automatic
update trust claim is made.

## Verification gates

| Gate | Result |
|---|---|
| Release operations unit/integration | 4 passed |
| Persistence backup regression combined | 8 passed |
| Clean-profile install/update/rollback/uninstall/reinstall | passed |
| Extracted ZIP exact manifest | 4,644 files passed |
| Packaged helper entrypoint smoke | 4/4 passed |
| Unity PlayMode | 55/55 passed |
| Repository | 338 passed, 10 explicit opt-in native/Unity skips |
| Browser runtime | 7/7 passed |
| Static/contracts | Ruff passed; strict mypy passed across 184 source files; schemas fresh; compileall passed |

Machine-readable acceptance: [`p15-windows-release/acceptance.json`](p15-windows-release/acceptance.json).
Operations runbook: [`../runbooks/SORA_INSTALL_UPDATE_UNINSTALL.md`](../runbooks/SORA_INSTALL_UPDATE_UNINSTALL.md).

Roadmap after P15.3: **80/91 checklist items (87.9%)**. P15.4 is next; P15.2's physical-phone gate
remains independently open. No commit, tag or staging operation was performed.
