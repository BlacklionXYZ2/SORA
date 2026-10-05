# GUI-3c canonical Memory chooser and Chat evidence

Model name: **GPT-6.1 Sol**. Source checkpoint: **2026-10-04 10:45:52 +01:00**. Status: **source integration and component verification; GUI-3c in progress**. Extends the [presentation transport contract](GUI3_MEMORY_PRESENTATION_CONTRACT_GPT-6.1-Sol_2026-10-04.md), not its native acceptance.

## Calls and authority

The enabled compact schema adds two closed operations:

```json
{"op":"find_memory","query":"preferred editor","cursor":null}
```

```json
{"op":"present_memory","target":"m<turn-nonce>-r1"}
```

`query` is a literal canonical content search, bounded to256 characters. Optional `cursor` is an issued opaque query-bound continuation, not a SQL cursor or filesystem path. `target` is an opaque reference issued for this turn and exposed in an actual bounded observation, never a raw Memory ID. Extra fields, caller authority, coordinates and paths are invalid. Disabled operations disappear from the filtered schema.

Core derives owner/project/Core identity and the presentation's origin/activation/dialogue correlation. The chooser cannot change settings, grant itself access, correct/forget a memory or manufacture a success. `present_memory` is offered only for an explicit owner request to show/open/inspect a memory, with a registered host and enabled memory context. Quoted, negative, hypothetical and discussion/capability wording is excluded by a conservative intent check. This is a source-tested intent heuristic, not universal natural-language understanding.

Initial canonical memories are separate compiler items. Only included memory items appear in the chooser preview. Lookup uses the existing owner/current-project-plus-global active canonical browser,10 records per page, durable/nonsecret records only. It does not read capture files, rank semantic relevance or expose private evidence paths. The existing static local-policy direction remains unchanged; this feature adds no per-file approval workflow.

## Reference lifecycle and limits

- References are process-local and turn-local, with a random nonce; no persistence or new client Memory store.
- At most64 ID/version targets and6 issued continuation references per turn; repeated exact target versions reuse a locator.
- Reference/lookup lifetime is60 seconds. A continuation must match its issued literal query; cross-turn/invented/unexposed/expired references fail closed.
- Snippets are limited to300 characters. Bounded-observation trimming is applied before exposure; trimmed targets cannot be selected merely because Core issued them internally.
- Core resolves the exposed reference to exact ID/version. Admission and acknowledgement still revalidate canonical scope/deletion/version/host/Core/deadline under the transport contract. Correction never silently redirects a stale reference to a successor.
- Projection/SQLite lookup failures yield a redacted unavailable explanation. Invalid canonical rows during later dialogue context reconstruction are withheld, with an unavailable-context note rather than stored values entering model/error text.

## Retrieval evidence is not model reasoning

`memory.retrieved` records `retrieval_id`, `dialogue_request_id`, `instance_id`, stage `chooser` or `reply`, source `canonical`, and an array of canonical `memory_id` / `entity_version`. Event/outbox publication uses the existing repository transaction without changing the Memory projection revision. Identical stage/target sets are deduplicated within the turn.

Chooser publication uses the references actually remaining in that step's bounded observations, not the cumulative set exposed in previous steps. Reply publication uses included compiled memories and surviving read observations supplied to the response path. Publication describes Core's context selection/supply attempt; it does not prove a model consumed the data, reasoned about it or generated a reply. No private capture rationale, memory content, snippet, opaque locator, paths, lease or screen bounds enter this metadata.

## Acknowledgement-aware response and Stop

Core dispatches one exact presentation and waits while its result is pending. An ordinary conversation response does not claim success from enqueueing. A selected/already-visible result returns a deterministic host-confirmation receipt; negative/expired/unavailable results explicitly withhold opening/highlight confirmation. This is a host report, not independent Windows attestation or an avatar POINT gesture.

Turn cancellation retires an unacknowledged request; a late fake-host ACK cannot turn a cancelled pending request into success. The shared Memory form also reads the current pending result after its exact canonical detail read and immediately before selection. This narrows the read/cancel race; it is not atomic across Windows UI and SQLite, and an already-dispatched UI effect is not promised undoable. Existing draft/modal/focus/minimize/dismiss/layout/expiry protections remain.

## Chat projection and exact navigation

The shared `WidgetMemoryActivity` parser accepts only bounded, typed metadata for `memory.retrieved` and terminal `ui.memory.presented` events. Core identity, event sequence/time, IDs, positive version, retrieval stage/source and presentation binding/status are validated. Unknown/private fields are not copied. Pending/queued/dispatched/unknown statuses cannot become success chips.

`WidgetSync` deduplicates by event-plus-record, retains the latest64 entries, preserves marked stale cache during disconnect and clears it on resync/new Core. Shell renders at most6 current-Core Memory chips beside task chips. Retrieval says **Memory context selected**; positive presentation says **Memory selected · host report**; negative statuses remain distinct. Correlation is inspectable, not fabricated association with a canonical Chat message. Historic chips are not proof of current panel visibility or model thoughts.

Clicking requests the recorded exact ID/version through the guarded shared owner-local route. Dispatch is labelled requested, not selected. It does not activate an unrelated panel, follow a successor or bypass retained drafts; the normal host acknowledgement path confirms selection. No second poller or schema/settings/database migration is added.

## Acceptance boundary

[Verification](../verification/GUI3_MEMORY_COMPANION_GPT-6.1-Sol_2026-10-04.md) separates deterministic HTTP/fake-host and pure C# coverage from actual native/live inference. Required remaining acceptance includes real small-model selection, connected native Chat-to-Memory/chip navigation, exact highlight/geometry, draft/modal/focus/Stop/epoch/version handling, keyboard/DPI/high contrast and normal restart availability. This contract does not close GUI-3c or Milestone B.
