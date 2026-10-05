# GUI-3b canonical Memory correction/forget progress

Model name: **GPT-6.1 Sol**. Implementation checkpoint: **2026-10-04 09:14:38 +01:00**, Europe/London. Status: **implemented slice / stage in progress**. No native acceptance or stage-completion timestamp.

## Implemented changes

- Added closed MemoryCorrection/MemoryForget/MemoryMutationAck contracts and three exported schemas. Owner-local POST correction/forget and read-only receipt routes, mandatory body Core-instance fencing, standard typed conflict/error shape and scope-safe redacted errors; remote/paired routes remain unavailable.
- Added migration11 durable owner/project/request receipts and atomic SQL scope/state/version validation, successor/soft-delete, global revision, public event/outbox and receipt commit/rollback. Existing canonical storage/raw callers preserved, no competing client memory database.
- Correction generates one successor with inherited scope/sensitivity/retention/expiry and owner-derived provenance; original evidence is not carried over as support for new text. Forget affects only an exact versioned record, including inactive records; excludes retrieval/browser without promising capture/backup/transcript erasure or Undo.
- Idempotent same-intent retries/receipt reads report the original historical commit without another effect/revision. Mismatched reuse conflicts. Receipts contain IDs/versions/digests, not corrected content/private captures/paths; malformed canonical data stays redacted.
- Added shared Memory correction editor, explicit forget consequences, exact-ID baseline review, frozen unknown requests/receipt check/explicit same-key retry, hide retention, mutation/modal/draft-aware host Quit and closed acknowledgement validation. Core-down/new-instance drafts are retained rather than retargeted/replayed; no model or extra poller/store.
- Added20 lifecycle HTTP/SQLite/migration/context/restore cases and20 C# pure/session cases, including Unicode-scalar bounds. Contract/runbook/roadmapv1.24/verification and a dated host/interface note updated; earlier stages/attribution/originals preserved.

## Verification and boundaries

[Verification](../docs/verification/GUI3_MEMORY_MANAGEMENT_GPT-6.1-Sol_2026-10-04.md): focused48 checks passed,**329 C# passed**, all three final zero-warning/error Windows builds and effect-free forwarding pass. Final Python regression: **765 passed /25 opt-in skipped in90.61s**, **8 PWA passed**, mypy272/lint/schema/compile; exec27984 normal exit0 observed by **2026-10-04 09:20:32 +01:00**. Earlier full762 Python/25 skipped/8 PWA is labelled before final context/corrupt-record refinements; the final C#-only Unicode/admission-rejection refinements were separately verified through329 checks/builds. Failed initial test harness/typing/lint checks were repaired and rerun; no failed result is claimed green. This verification time is not native stage completion.

Owner runtime/settings/data unchanged; no native GUI/paid provider/physical voice or permission-workflow bypass. AppSettingsv9/UIpreferencesv1/default Desktop remain unchanged. Migration11 is source/tested only, not applied to owner storage. New routes become available after a later normal restart. Original overview/reference/earlier plans, all completed dates and previous model logs are preserved. No reset, commit or material deletion. Full GUI-3b/native/earlier/scheduler/graph/release acceptance remains open; full GUI goal remains active.

Final C#-only admission-rejection refinement: **2026-10-04 09:23:51 +01:00**,329 passes/three final zero-warning-error builds. Definite rejection no longer freezes a draft as an uncertain write; request-binding/server/transport failures remain frozen. No Python source change after its final765-pass run.

## Final preservation/documentation checks

Read-back at **2026-10-04 09:22:43 +01:00** found **157 local links, zero broken**, across six changed/new delivery documents; count/date and final C# addenda were subsequently read back. Exactly GUI-0a/0c/0d remain checked at **2026-10-03 19:24:55 +01:00**. Git whitespace check exits0; untracked artifacts are explicitly built/tested/read back rather than assumed covered by Git.

The1006-file fingerprint taken before the preceding documentation reconciliation covers that pass plus this implementation:13 declared existing-file changes,993 unrelated pre-existing files byte-identical, no missing files, and11 additions (including the preceding documentation-only changelog). All9 original reference/overview/draft artifacts and all previous contributor logs remain byte-identical. This is preservation/verification evidence, not native stage closure.
