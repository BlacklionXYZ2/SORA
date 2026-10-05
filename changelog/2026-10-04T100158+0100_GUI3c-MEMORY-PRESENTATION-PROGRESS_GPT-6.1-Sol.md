# GUI-3c Memory presentation transport/host progress

Model name: **GPT-6.1 Sol**. Implementation checkpoint: **2026-10-04 10:01:58 +01:00**, Europe/London. Status: **implemented source slice / stage in progress**. No native or stage-completion timestamp.

## Changes implemented

- Finalized and exported eight closed Memory presentation/host contracts. Integrated the hub with runtime/Core-instance ownership and owner-local leased registration/poll/request/ack/result routes; mandatory body identity, strict scope/version/queue/expiry and redacted errors. Initial host registration can reconcile a lost reply without issuing another live lease.
- Added bounded transient queue/dedup/history, concurrent admission fencing, cancellation/host loss/new-Core behavior and exact acknowledged target checks. One SQL transaction rechecks canonical version/deletion/current deadline/host/generation and publishes content-free event/outbox; cancellation observes a shielded write, duplicate identical ACK returns one historical event, changed ACK conflicts. No database migration, Memory revision change or restart-durable UI-effect claim.
- Added a pure shared C# protocol/client with exact binding/positive-ACK validation, bounded batch/cache and uncertain-callback suppression. Only the opt-in Shell registers through its existing refresh; model-down operation and compatibility clients remain independent. No new poller/settings/client memory store.
- Connected the shared Memory form's fresh exact-ID/version read, static accessible highlight and actual screen anchor without window activation. Draft/read/modal/effect/dismiss/minimize/deadline/epoch/generation guards protect user work; layout/target/Core/expiry changes clear emphasis. Host Quit respects pending presentation. Lost transport replies reconcile ACK only, never repeat selection; invalid/negative confirmation marks inspection stale.
- Added23 real HTTP/SQLite transport cases and20 C# protocol/client/session cases. Historical host keys prune five minutes after expiry, preventing permanent saturation of a continuously renewed host. Updated roadmap/runbook, added contract/verification documents. Preserved earlier source/contributor history and original reference/overview/plan files. Existing validated project-mode selection now uses a formatter-safe explicit type cast without changing routing behavior.

## Verification and boundaries

[Verification](../docs/verification/GUI3_MEMORY_PRESENTATION_GPT-6.1-Sol_2026-10-04.md): focused69 checks passed,349 final C# passed, all three final zero-warning/error Windows builds and effect-free launcher forwarding. Full isolated regression session93829 is recorded only after terminal completion in the verification addendum.

No native GUI or live model/provider/physical acceptance; owner Core/settings/data unchanged, no runtime restart/migration/reload or denied-workflow retry. AppSettingsv9/UIpreferencesv1/default Desktop unchanged. No stage checkbox/date is advanced. Full goal active.

**Remaining GUI-3c work:** small-model `present_memory` and issued actually exposed canonical Memory refs; actual public retrieval/activity IDs and acknowledged Chat chips; turn-aware response coordination; ordinary conversational/native/live/physical acceptance. This transport/host slice is not a substitute for those requirements or proof of the full GUI goal.

Final Python regression observed **2026-10-04 10:05:02 +01:00**, exec93829 terminal exit0: **788 Python passed /25 opt-in skipped in94.66s; 8 PWA passed; mypy275/lint/schema/compile passed**. Earlier348 C#/three zero-warning-error builds were verified at10:01:58. Final C#-only host-cache expiry refinement: **349 passed and three zero-warning/error builds at2026-10-04 10:10:49 +01:00**. Python/contracts remained unchanged after the full run. Documentation updated tov1.26; no stage-completion time claimed.

## Preservation and documentation checks

Checkpoint **2026-10-04 10:08:45 +01:00**:148 local links across five delivery documents, zero broken; all five manifest originals match sizes/SHA-256, exactly the original three stage checkboxes/dates retained, Git whitespace exit0. Later C# expiry refinement and its dated documentation addenda remain within the declared files.

The1020-file fingerprint taken before the preceding v1.25 documentation reconciliation covers that pass plus this implementation:11 declared existing-file changes,1009 existing files byte-identical, no missing files,15 additions including the preceding documentation-only changelog. All9 reference/overview/draft originals and prior pre-existing contributor logs are preserved. No reset, commit or material deletion.
