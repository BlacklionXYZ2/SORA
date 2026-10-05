# W4 native read foundation — GPT-6 Astra

Completed slice: **2026-10-02 12:40:18 +01:00** (Europe/London).
Status: **implemented and partially user-side verified; W4 and the frontend goal remain in progress**.

## Changes implemented

- Extended desktop contracts and the process-isolated Windows helper with cross-process
  inventory and bounded UIA text/selection reads, pattern-availability flags, password redaction,
  process identity and combined text budgets; regenerated public schemas.
- Added `companion_read` contracts, the local-model structured selector, transient filesystem/
  window readers and a six-step bounded read orchestrator. No shell or direct writing tool added.
- Connected ordinary local chat to Desktop metadata, file discovery/search/read and native
  inspection under static settings, with epoch rechecks and remote/hosted-model separation.
- Added source/outcome/time notes, honest partial/unsupported statuses, explicit selection mode,
  fresh-evidence-first context compression, and protection against stale answer-history reuse.
- Kept native reading independent of screenshot and avatar switches. Preserved existing remote
  grants and existing attachment handling; did not mint local read grants.
- Wired the native helper into the one-command startup path, surfaced actual managed-model names,
  and moved Companion access to the beginning of the schema-driven Settings page.
- Added 19 focused read tests plus an opt-in native/real-model fixture, expanded settings tests,
  and documented launch/read behavior and the exact remaining acceptance gaps.

## Verification and limits

- Full verification: **513 Python tests passed, 14 opt-in skipped; 7 PWA tests passed**; Ruff,
  mypy (222 files), generated-contract freshness and compileall passed.
- **36 C# tests passed**. Windows helper, UIA fixture and isolated desktop app builds passed.
- Real native fixture passed. Final live Gemma 4 E2B IQ4_XS/Core/native selected-text tests passed
  twice; the final assertion checks exact `bef` and confirms no click/type mutation.
- GUI window listing and unattached file discovery/read passed. GUI review found and drove fixes
  for the managed model alias, oversized context, buried access settings and selection handling.
- Corrected selection and final Settings ordering still need GUI rechecks. No claim of full W4,
  ordinary-launch, passive perception, voice, action or agent-catalogue completion is made.
- All live conversations/configuration used isolated `.local/native-read-qa-20261002` state and
  the local Gemma model. No paid agent task, owner-state migration, commit or owner-file deletion.

Detailed evidence and remaining requirements:
[W4 verification](../docs/verification/W4_NATIVE_READ_PROGRESS_GPT-6-Astra_2026-10-02.md).
