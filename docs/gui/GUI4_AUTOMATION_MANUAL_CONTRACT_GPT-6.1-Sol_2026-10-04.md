# GUI-4 durable manual Run now

Model name: **GPT-6.1 Sol**. Source checkpoint **2026-10-04 13:44:05 +01:00**, Europe/London. Status: **source/component slice implemented; GUI-4a/c in progress**. Extends the [worker contract](GUI4_AUTOMATION_WORKER_CONTRACT_GPT-6.1-Sol_2026-10-04.md) and [full Automation contract](GUI4_AUTOMATION_CONTRACT_GPT-6.1-Sol_2026-10-04.md). No shared Automations panel or live-provider/native acceptance is implied.

## Owner-local operation

`POST /api/v1/automations/{id}/run-now` accepts the new closed exported `AutomationRunNow` contract: mandatory current `instance_id`, stable UUID `request_id`, strict positive `expected_version`, and optional literal `action: run_now`. It accepts no owner/project authority, replacement behavior, provider/model override, caller permission, raw tool or path. It runs the exact saved behavior. Both active and paused definitions permit this explicit manual request; deleted/foreign definitions do not. Paused still suppresses scheduled admission.

New accepted attempts return202; identical replay200. These are acceptance of a durable attempt, **not task admission or completion**. Existing owner-local authentication, remote403, shutdown fence, instance409, scoped/version404/409, closed-body/query400, methods405 and redacted storage503 remain. A header/body instance mismatch cannot authorize effects. Request-key conflicts are409, including trying to reuse a create/edit key for Run now.

## Atomic reservation and historical receipt

One SQL write transaction checks scope/version, snapshots exact definition/behavior, stores a distinct `origin: manual` occurrence with `manual:{request_uuid}` slot key and a unique scoped submission key, advances revision and publishes content-free event/outbox metadata plus the durable historical receipt. Definition version/state/timestamps and the persisted scheduled next slot are **unchanged**. Manual slots record the actual requested instant/timezone; they are not a substitute recurring schedule or shifted due time.

If another reserved/admitted/unknown occurrence exists, the new attempt is skipped with `skip_overlap`. If the worker is unavailable/stopped/stopping, the new attempt is blocked with `scheduler_unavailable`, not a latent run that silently starts later. Running/degraded worker states permit a reservation; later policy/provider/project/definition failure is visible through canonical history. A racing shutdown is still fenced at actual task admission. No unsupported adapter, inferred model entitlement or automatic retry is introduced.

`AutomationAck` adds literal action `run_now` and optional occurrence. Its closed validator permits an occurrence only for that action and checks manual origin, exact definition/version/behavior/request slot and unadmitted status with no task claim. Old mutation receipts remain compatible with occurrence absent/null. A saved manual receipt freezes the original reserved/skipped/blocked snapshot and original committed epoch; replay rebinds only current transport epoch and replay flag. Later task admission/status, definition edits/delete or a restarted Core do not rewrite it. Use exact history to inspect current occurrence outcome; a receipt is never proof of current worker state or visible UI.

The owner/project-scoped existing receipt table is reused. No migration, competing JSON store, client-side execution or new specialist runtime. Changed payload/target/version under the same key conflicts. Event/outbox failure rolls back occurrence, revision and receipt. Events include IDs/version/origin/status/reason only, not the behavior, model transcripts or owner paths.

## Admission, restart and expiry

The existing owned worker processes reserved manual attempts using the same guarded canonical task transaction/queue handoff as scheduled occurrences. It still rechecks exact current definition/version/behavior, overlap and fresh static delegation/provider policy/epoch. Pause/edit/resume/delete changing the version before admission retires that request; pause does not cancel a task already admitted. A paused definition's explicit Run now is allowed without activating its schedule.

Unadmitted manual requests expire after **300 seconds** from their persisted request instant. This is a product admission limit, not the recurring trigger's catch-up setting. Recovery within that window may admit the already-accepted request if no exact submission exists; after expiry it records `manual_request_expired` and does not launch. Expiry is also checked at SQL admission. Existing exact submission evidence is reconciled without scheduler resubmission/re-enqueue, and Unknown work continues to block overlap. Clock rollback leaves a future manual request waiting. No automatic external-effect replay or exactly-once external-effect claim.

The endpoint returns a durable reservation without waiting for a provider. A lost HTTP response therefore reconciles through `GET /api/v1/automation-requests/{uuid}` before any deliberately repeated same-key request. Never generate a new key merely to recover a transport failure; a new key is a distinct explicit user attempt and remains subject to overlap.

## Verification and remaining UI scope

[Verification](../verification/GUI4_AUTOMATION_MANUAL_GPT-6.1-Sol_2026-10-04.md) includes actual temporary authenticated HTTP/SQLite manual task completion and temporary Core reopen within/after expiry, using a deterministic provider and injected clock boundaries. It does not verify a native control, actual model/provider entitlement or owner-runtime restart.

Next deliver the shared profile/Core-bound Automations window from [the original reference](reference/03-automations.jpg): bounded All/Active/Paused/search and exact selection; Overview/Edit/Logs; full retained New/Edit draft with all supported trigger/behavior/missed-policy fields; pause/resume/delete/explicit Run now and historical receipt reconciliation; exact task Cancel/run/evidence navigation; supported provider/model/purpose/project/tools data, not illustrative fake adapters. Add the missing narrow last-outcome projection if needed before displaying a last-run label, and distinguish request/reservation timestamps from real task completion. Reuse the shared session/poller and UI-only preferences; no raw JSON editing requirement, separate canonical store or duplicate agent runtime. Then integrate semantic `present_automation` and obtain connected native/live/physical/accessibility/release acceptance. All earlier gates and full GUI goal remain open.
