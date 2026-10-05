# GUI-3c Memory presentation transport and host selection contract

Model name: **GPT-6.1 Sol**. Source checkpoint: **2026-10-04 10:01:58 +01:00**, Europe/London. Status: **implemented transport/host slice; GUI-3c in progress**. This is not completed conversational or native acceptance.

## Delivery boundary

Core now owns a bounded transient Memory-only host registry and presentation queue. The opt-in desktop Shell renews/polls through its existing shared session refresh, resolves the exact canonical record, selects and statically highlights it without activating a window, and submits a closed acknowledgement. Compatibility clients/prototype do not register. No new inference engine, timer, client memory database, AppSettings field, persistence migration or recurring permission request.

The model `present_memory` chooser, issued per-turn memory references, public canonical retrieval events, Chat memory chips, conversation-to-panel response coordination and real/native acceptance remain required follow-on GUI-3c work. The owner-local request endpoint is transport, not proof that a conversation can invoke it. Avatar POINT/control-reference routing is not implemented by this slice. Keep the earlier browser and versioned management contracts unchanged.

## Exported contracts and owner-local routes

Eight `schema_version=1.0` closed contracts are registered/exported: `UiHostRegistration`, `UiHostLease`, `UiHostCommand`, `UiMemoryCommand`, `UiMemoryPresentation`, `UiPresentationPage`, `UiPresentationAck`, `UiPresentationResult`.

| Route | Request and meaning |
|---|---|
| POST `/api/v1/ui/host` | Exact Core UUID, process host UUID, opaque profile key, nullable previous lease, nonnegative bounded registry generation and only the Memory panel. Renew the same active lease; conflicting host/profile/lease or decreasing generation rejects |
| POST `/api/v1/ui/presentations/poll` | Exact Core/host/lease body; return at most16 pending requests. Polling does not select a record or publish success |
| POST `/api/v1/ui/present-memory` | Owner's exact Core/request UUID, canonical Memory ID and strict positive expected version. Core derives owner/project and owner/explicit origin. Response is pending, never opened/selected from dispatch |
| POST `/api/v1/ui/presentations/ack` | Exact bound target/request/Core/host/lease/version/generation, outcome, visibility/selection/highlight and optional current screen anchor. Core validates and rechecks canonical scope/version before publishing the result/event |
| GET `/api/v1/ui/presentations/{request_uuid}` | Transient result lookup, not a durable UI receipt or new effect |

All routes reject paired/remote callers with403, unsupported methods with405, extra query parameters/oversized bodies with400; POST bodies cap at8192 bytes. Core-instance header fencing remains available; the closed body also requires the current instance. Missing/cross-scope/deleted IDs and absent results are404. Typed binding/version/queue conflicts are409; canonical projection failures are redacted503. Caller authority, origin, activation or arbitrary desktop commands cannot be added to the owner request.

Profile keys are opaque routing identities, not grants or independent OS attestation. The authenticated Shell first validates the Core's state-root identity using its existing profile/session binding; host leases remain process-local credentials in private request bodies, never URLs, UI preferences, public events or changelogs. Initial same-host/profile registration retry can recover a lost lease reply without a second active lease.

## Lifetimes, retries and event meaning

- Host lease:30 seconds, renewed by the shared refresh. Presentation request:15 seconds. Core enforces monotonic deadlines; public expiry timestamps are timezone-aware. Registry generations fit signed64-bit integers. At most32 pending and256 retained requests; at most16 in a poll; terminal results prune five minutes after the request deadline.
- Request UUID binds exact target/version/origin/activation/dialogue correlation. Same binding returns its earlier transient result; changed binding conflicts. A concurrent canonical read cannot admit the same key twice. No automatic selection replay after Core/host loss. New Core clears all old registry/queue bindings; results are intentionally not restart-durable.
- Success requires `selected` or `already-visible`, visible panel, exact selected ID/version, highlight and positive-size screen anchor. Non-success may not claim a highlight/anchor. Duplicate identical acknowledgements return the same historical result; changed acknowledgements conflict. A historical acknowledgement is not proof that the panel remains visible now.
- Acknowledgement writes recheck deadline/current host/generation and canonical scope/version inside the SQL transaction. Target correction/deletion produces unavailable/target-changed, not a successor or nearby selection. Event/outbox publication rolls back together on failure. Cancellation of a response wait observes the shielded write before caching its result, preventing a duplicate event on retry. Turn cancellation before acknowledgement is terminal rejected; it does not undo an already selected UI or committed acknowledgement.
- `ui.memory.presented` can describe **selected, already-visible, deferred, unavailable or rejected**. Consumers must inspect status, not infer success from the event name. Payload contains only request/memory/version/status/host/Core/generation/dialogue IDs; no content, captures, private rationale, leases or screen bounds. It does not change the canonical Memory revision. Paired event sanitation excludes the payload/IDs. The event records an authenticated host report plus canonical target validation, not independent observation of Windows.

## Host selection and user control

Selection first performs a bounded fresh exact-ID detail read. Core epoch, target version, interaction generation and expiry must still match afterward. It does not retarget an edit, discard a draft, select a fallback, activate the window or require a working model. Retained Memory drafts, reads, modals, task/settings/voice operations and host Quit take precedence. Passive requests require an already visible, non-minimized panel. Explicit requests may show it without activation, but cannot reopen a panel dismissed after that request was created or restore a minimized panel.

Static accessible inspector emphasis follows exact accepted selection. Actual `RectangleToScreen` bounds are clipped to the current screen; no invented anchor. Manual selection/filter changes, resize/move/DPI/scroll/visibility changes, Core loss and expiry clear the highlight and advance generation. Negative or malformed Core confirmation clears emphasis and marks inspection stale. Quit includes presentation work in its pending-work guard.

The host records an intent before invoking selection. An uncertain callback never runs again for that request key. Lost transport replies may resend the frozen acknowledgement only while the same actual selection/highlight generation remains valid and unexpired; changed layout/expiry cannot send a fresh positive acknowledgement. Historical host keys prune five minutes after expiry, so a continuously renewed host does not become permanently full after256 requests. This is acknowledgement reconciliation, not UI-effect replay. No atomicity across Windows and SQLite is claimed.

## Remaining acceptance

Actual native show/select/highlight/anchor/focus/dismiss/minimize/draft/modal/Quit/DPI/screen-reader operation is unverified. Pure predicates and successful builds are not those tests. **Later companion integration:** [chooser/retrieval/Chat contract](GUI3_MEMORY_COMPANION_CONTRACT_GPT-6.1-Sol_2026-10-04.md) and its verification now record the connected deterministic HTTP/fake-host path. This supersedes the transport checkpoint's unconnected-model wording, not its native/live boundaries. Known Memory found/opened from ordinary native Chat and a real small local model's action selection remain unproven; these and all earlier GUI gates are required before GUI-3c/Milestone B can close.
