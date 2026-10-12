# Cleanup script for .local leftovers; release acceptance no longer leaves full test installs

Model name: **Opus 5.5**. Checkpoint **2026-10-09 08:40:00 +01:00**, Europe/London. Status:
**implemented. The dry run was checked; nothing was removed** (the owner removes with `-Remove`).
The owner asked why `.local` held about 40 GB, which items were safe to remove, and for a script.

## Findings

- **`.local/releases`, 14.5 GB:** 23 full release builds and zips from P15.3–P15.8 acceptance
  retries (22–23 September). Each is 0.6–1 GB, because `build-release.ps1` publishes four
  self-contained single-file helpers (about 110–125 MB each, with their own .NET) plus the Unity
  player and an embedded Python.
- **8 `p15.3-release-acceptance-<guid>` folders, about 13 GB:** `verify-release.ps1` installs each
  run into a new folder and never removes it. There are also 2 `p15.3-archive-extract-*`
  folders, about 1.5 GB.
- **`p15.3-python`, 3.35 GB:** mostly an obsolete Unity 2022 installer (3.27 GB). `toolchains` is
  a link to the same folder.

## Changes

- **New `scripts/cleanup-local.ps1`:** a fixed list of 23 items (22.3 GB).
  - Every item was checked on 2026-10-08: nothing runs from it, and nothing in `docs/` or
    `changelog/` refers to it.
  - It lists by default and removes only with `-Remove`.
  - It skips links and items that are already gone.
  - It excludes everything cited as evidence, the owner's profile, voice, and the working
    decision layer.
- **`scripts/verify-release.ps1`:** after a successful run, with a work root it generated itself,
  it copies `acceptance.json` beside the bundle and removes the temporary install. Failed runs
  and `-WorkRoot` runs keep it, and so does the new `-KeepWorkRoot` switch.
- The install runbook documents both.

## Verification

- Both scripts parse with no errors (Windows PowerShell 5.1 parser).
- The cleanup dry run listed all 23 items, 22.3 GB in total.
- **Not run:** `-Remove` (the owner's decision), and a full `verify-release.ps1` run, which would
  need a fresh release build.

HOW_TO_USE.md: no change to usage.
