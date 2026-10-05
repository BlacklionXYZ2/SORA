# GUI-4a canonical Automation storage/API/reservations

Model name: **GPT-6.1 Sol**. Source checkpoint **2026-10-04 12:48:42 +01:00**, Europe/London. Status: **source slice implemented/component-tested; GUI-4a in progress**. Extends the [full Automations contract](GUI4_AUTOMATION_CONTRACT_GPT-6.1-Sol_2026-10-04.md); no worker/task dispatch/UI delivery is implied.

## Migration and canonical state

**Later source update, 13:23:16 +01:00:** The [worker contract](GUI4_AUTOMATION_WORKER_CONTRACT_GPT-6.1-Sol_2026-10-04.md) delivers timing, task admission/linkage and conservative recovery. This document preserves the earlier storage-only checkpoint, including its then-unavailable scheduler projections. Current list/detail report actual worker state; old save receipts retain their historical state. Manual Run now/shared UI and connected/live/native acceptance remain open.

Migration12 follows11, adding `automation_definitions`, `automation_occurrences` and `automation_mutation_receipts` plus scope/active indexes. Reuses canonical owners/projects/task/run foreign keys, entity versions and existing revision/event/outbox transactions. No client JSON store, Core settings migration or agent runtime. Original rows/revisions survive the tested migration; owner Core/data are not migrated in this implementation pass.

Definitions retain typed behavior/trigger/state, true creation/update timestamps and next slot. Paused/deleted have no next slot; active with no future one-off slot is exhausted, not proof of work. Occurrences snapshot exact definition version/behavior, scheduled slot/status, unique submission key and optional real task/run links. This slice only creates internal reserved/skipped occurrences, never tasks or completed runs. Seven new closed API contracts are registered/exported alongside the four time/data contracts.

## Owner-local routes

| Route | Meaning |
|---|---|
| `GET /api/v1/automations?q=&state=all&limit=50&cursor=` | Bounded literal name search, All/Active/Paused summary page |
| `POST /api/v1/automations` | Create with current `instance_id`, stable `request_id`, full `spec` and optional `state`; defaults paused |
| `GET /api/v1/automations/{id}` | Exact scoped canonical definition and next slot |
| `POST /api/v1/automations/{id}` | Expected-version `edit` with full spec, or `pause` / `resume` / `delete` without spec |
| `GET /api/v1/automations/{id}/history?limit=50&cursor=` | Exact-ID occurrence history, including retained soft-deleted definitions |
| `GET /api/v1/automation-requests/{uuid}` | Durable original mutation receipt/reconciliation |

Paired/guest scopes return403; method mismatch405; invalid/extra/ambiguous filters/body/closed fields400; missing/foreign/deleted definition404; instance/version/state/request conflicts409; canonical corruption/database errors503 with generic messages. GET bodies and POST query parameters are rejected; POST body cap65536 bytes. Existing Core-instance header fencing remains. Body UUID identity is mandatory for effects; owner/project/state/provenance authority is not accepted from a caller.

**All returned saved-definition projections/receipts explicitly say `scheduler_state: unavailable`.** Active is the saved definition state, not worker availability. Save/reservation does not start an agent. Run now is not yet a supported route and must not appear as an operative UI control until the next worker/admission scope is integrated.

## Scope, reads and paging

Owner/current-project plus owner-global definitions are visible; foreign owner/project IDs cannot be read or edited. Creates bind to the configured current project. Receipt keys are owner/project-request scoped, so one project's request UUID cannot fetch another project's mutation.

List summaries contain name/state/version/trigger kind/timezone/next slot, not private behavior, paths or capture rationale. Exact detail/history are deliberate owner-local inspectors; they can contain the owner's stored behavior snapshot. Public mutation/reservation events contain IDs/version/state/status/reason only, not behavior/name/intent/provider transcripts. No capture-file reads or private reasoning.

Page sizes1–50, query≤256 characters; at most256 scoped definitions are scanned per list request. An empty matching page may still have a progressing continuation. Cursor HMAC binds Core epoch/key, owner/project, view/query/state/limit/target, admission ceiling and next ordinal. No later insert enters an existing traversal; filters/states/outcomes may change between deliberate requests. Cursor is signed, not an encrypted storage mechanism or bearer authority. New store/Core invalidates it. Definitions/history and revision are read in one SQLite snapshot, with standalone read transactions rolled back without touching an enclosing write.

## Mutations and historical receipts

One SQL write transaction checks target scope/version/state, applies mutation, advances revision and appends public event/outbox plus durable receipt. Identical replay returns the exact original acknowledgement/event/definition snapshot, rebound to current transport instance with original committed instance retained. Changed payload under the same scoped key conflicts. No second mutation/event from concurrent identical requests. Receipt is historical, not current state or task success; it survives delete/new Core.

Edit requires a full typed spec and cannot silently move a definition's project. Active label/description/behavior edits with an unchanged trigger preserve its next slot; trigger change recalculates. Pause requires active, clears next slot; Resume requires paused and computes future scheduling rather than bursting paused backlog. Delete is soft history exclusion, not erasure or task cancellation. A separately admitted task would require its own existing task Cancel; this slice admits none.

## Internal reservation foundation

`AutomationStore.reserve_scheduled` is internal, not an API action or functioning scheduler. It atomically validates scoped active definition/version/exact persisted slot, applies the pure due/missed/overlap policy, inserts one unique scheduled occurrence/submission key, advances the next anchored schedule and emits content-free revision/event/outbox metadata. Future slots return no reservation/event. Duplicate exact reservation returns the existing occurrence without another advancement/event. Concurrent reservation/reopen retains that unique result and behavior snapshot.

Reserved/admitted/unknown work blocks overlap for that automation. A skip records its reason; missed recovery advances beyond the current observed time without enumerating/admitting a backlog. `missed_until` metadata describes the omitted range boundary, not a fabricated number of runs. No automatic retry or completed-status inference. Current reservation overlap is conservative until the upcoming worker reconciles canonical task outcomes.

## Next and acceptance limits

The next source scope is worker lifecycle, admission guards in the existing task transaction, exact task/run/submission linkage, conservative crash/unknown reconciliation, bounded scheduling/catch-up and manual Run now. Old-version reservations must be retired/rejected after pause/edit/delete before admission. Worker availability/status contracts must change truthfully only when that service is integrated. Then shared Automations list/detail/editor/logs and owner-side controls follow.

[Verification](../verification/GUI4_AUTOMATION_STORAGE_GPT-6.1-Sol_2026-10-04.md) covers actual temporary authenticated HTTP/SQLite storage plus internal reservation fixtures. No real scheduled task, native UI, live-model/provider or ordinary-release acceptance is claimed. Full GUI goal and all previous connected/native/live gates remain open.
