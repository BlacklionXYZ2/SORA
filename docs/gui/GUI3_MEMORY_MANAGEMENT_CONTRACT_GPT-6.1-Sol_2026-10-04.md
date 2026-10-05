# GUI-3b — canonical Memory correction and forgetting

Model name: **GPT-6.1 Sol**. Source checkpoint: **2026-10-04 09:14:38 +01:00**, Europe/London. Status: **implemented source slice / stage in progress**, native acceptance open. This extends the [GUI-3a browser contract](GUI3_MEMORY_BROWSER_CONTRACT_GPT-6.1-Sol_2026-10-04.md), not a second memory engine.

## Owner-local closed operations

All operations use the existing private authenticated Core API. Remote/paired scopes are refused403 regardless of claimed memory scopes. Owner/current project come from Core configuration, never caller assertions. Eligible targets are that owner's current-project or owner-global canonical records. Unknown/foreign-project/foreign-owner/deleted targets return404 with no content, private version or alternate selection. Read browser/detail routes remain GET-only; no GET causes a mutation.

| Route | Request | Result |
|---|---|---|
| `POST /api/v1/memories/{exact-id}/correct` | `instance_id`, UUID `request_id`, strict positive integer `expected_version`, meaningful non-NUL `content` up to16384 Unicode characters; optional schema_version1.0 | Typed MemoryMutationAck after canonical transaction commits |
| `POST /api/v1/memories/{exact-id}/forget` | Same identity/version fields, no content or extra authority/owner fields | Typed acknowledgement of exact-record soft deletion |
| `GET /api/v1/memory-mutations/{request-uuid}` | No query/body mutation; owner/current-project scoped receipt lookup | Historical committed receipt or404; absence does not prove an in-flight request cannot commit |

Query fields on mutation/receipt routes are invalid; mutation bodies capped at128KiB. Invalid closed requests return400 `INVALID_MEMORY_MUTATION`; wrong methods405. Mandatory body instance identity is compared even if the existing optional `X-SORA-Core-Instance` header is omitted. A stale body returns409 `CORE_INSTANCE_CHANGED`; a stale header retains409 `RUNTIME_CHANGED`. Shutdown admission fence also applies. Stored invalid records/receipts or database failures yield503 `MEMORY_UNAVAILABLE`, without private values/validation dumps.

409 conflicts use the ordinary `{error:{code,message,status,...}}` envelope. `MEMORY_VERSION_CONFLICT` / `MEMORY_STATE_CONFLICT` include only current permitted record version/state, not its content or another record's identity. `MEMORY_REQUEST_CONFLICT` rejects reuse of a request UUID with a different target, operation, version or content digest. No effect is admitted on these conflicts.

## Atomic canonical lifecycle

Migration11 adds `memory_mutation_receipts` to existing SQLite. It preserves existing memory rows and revisions; AppSettings staysv9 and UI preferences stayv1. No client JSON memory or mutation database exists. A serialized `BEGIN IMMEDIATE` write validates scope/state/version and commits memory changes, global revision, canonical public event/outbox and receipt together. Failure inserting a receipt rolls all changes back. Existing raw repository lifecycle methods remain available to their prior callers but are not exposed as safe GUI mutation APIs.

Correction is allowed only for an active nondeleted exact record. Core generates a successor ID/version1, inherits owner/project/scope/sensitivity/retention/expiry, updates the predecessor's superseded_by and increments its version. Provenance identifies an owner correction and request ID. Old evidence references are not copied: captures/links documenting old content are not evidence for a newly authored assertion. Expired/superseded targets cannot be corrected or silently renewed. Default canonical retrieval, and actual compiled dialogue Memory context, exclude the predecessor and use the eligible successor.

Forgetting is permitted for an active, expired or superseded nondeleted record at its exact expected version. It sets deleted_at and increments that version. It excludes only that ID from canonical retrieval and browser/detail results; it does not cascade to predecessors/successors. To forget a successor, inspect and forget that exact ID separately. Historical content remains in the soft-deleted SQL row; no Undo/restore operation is offered.

Private capture files are not read/exposed/erased by this operation. They continue through existing compaction/retention; the current compactor does not reconstruct SQL records. Conversation messages, audit events, backups and external agent transcripts remain. A backup taken before forgetting may contain earlier state; restoring it is not a physical-erasure guarantee. New backups preserve tombstones and receipts, as verified separately. New owner dialogue can independently remember a statement again; forgetting is not a permanent ban on future remembering.

## Receipts and uncertain outcomes

Receipts are keyed by owner, configured project scope and request UUID. Request binding hashes exact target/action/version and corrected-content SHA-256; it excludes the Core instance so an explicit same-intent retry can reconcile after restart. Receipts contain no raw corrected content, capture/reasoning data, tokens or paths. They persist with canonical storage; no expiry/pruning policy is implemented in this slice.

Acknowledgements carry schema1.0/current instance, committed_instance_id, request UUID, record owner/project/ID, action, expected/committed version, optional successor/version1/content digest, global committed revision, public event ID, aware committed_at, replayed flag and retention note. Event payloads carry exact memory/request/version/successor IDs, not private content or capture references. Receipt replays return the original commit metadata wrapped in the currently serving instance. They never renew, recreate, retarget or reapply the effect. `replayed=true` is historical confirmation, not proof that a successor still exists or is active.

Identical POST retry returns the receipt even after the target has been superseded/deleted; it does not add a revision/event/successor. Changed key binding conflicts. The GUI checks request/record/owner/project/action/version/epoch/content digest and successor/time/revision shape before declaring confirmation. A lost response, malformed acknowledgement, timeout or changed Core leaves the captured request unresolved; no automatic replay. Checking a receipt is a read only. An absent receipt does not automatically clear the request or generate a replacement key.

## Shared native interaction and truthful limits

Memory's **Correct…** opens a process-local text draft pinned to canonical ID/version/Core instance. **Save correction** commits that assertion. Browsing/navigation controls cannot retarget the draft. Hide retains it. A rejected conflict retains authored text; **Review latest** rereads the same exact ID and requires explicit owner acceptance of the displayed baseline, retaining authored text. Superseded/expired/deleted records cannot silently become a different correction target. New Core drafts require explicit review before a new mutation, not automatic migration.

**Forget…** confirms exact ID/version and the retention/backup limitations; this is an owner consequence decision, not a recurring permission application by SORA. Core/record freshness is rechecked after the modal and validated atomically server-side. Pending saves, receipt reads, navigation and modals protect host Quit. IPC Quit refuses unsaved Memory drafts; native Quit requires explicit local discard/continued editing. Hide does not undo or cancel a server write.

Uncertain requests freeze text/action/key. **Check receipt** may reconcile read-only across a new Core instance; **Retry same request** explicitly resubmits the same captured body/key only to its original current Core instance. Unknown outcomes are not automatically retried. Explicit discard warns that it does not undo an effect and displays an unresolved request UUID before losing the local draft. Drafts and request bodies are not persisted in UI preferences or public events; cross-host-restart draft recovery is not provided.

After an acknowledged commit, the page/detail is marked stale; the message names the exact committed target/successor and historical status. Refresh/explicit successor inspection is required for current state. No automatic successor selection, `present_memory` claim, retrieval pulse, relation graph or Undo. GUI-3c supplies acknowledged conversation-to-panel presentation; GUI-5 supplies real relationships/final visual design.

[Verification and remaining native acceptance](../verification/GUI3_MEMORY_MANAGEMENT_GPT-6.1-Sol_2026-10-04.md). Source/component proof does not establish actual focus/modal/layout/keyboard/DPI/accessibility or real-model behavior.
