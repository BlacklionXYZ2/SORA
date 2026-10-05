# GUI-3c presentation transport and host verification

Model name: **GPT-6.1 Sol**. Source checkpoint: **2026-10-04 10:01:58 +01:00**, Europe/London. Status: **implemented source slice; GUI-3c in progress**, not native/conversational acceptance.

[Contract](../gui/GUI3_MEMORY_PRESENTATION_CONTRACT_GPT-6.1-Sol_2026-10-04.md): eight exported contracts; bounded owner-local leased registration/poll/request/ack/result API; atomic scoped/versioned event/outbox publication; shared host exact selection/static highlight/anchor and retained-edit/focus/deadline/dedup guards. No settings or database migration.

## Fresh evidence

- Focused actual temporary HTTP/SQLite suite: **69 passed in6.99s** (23 new presentation cases,20 existing mutation cases,26 browser cases). No owner data or paid provider. Source fixture uses authenticated fake host acknowledgements, not a Windows observer.
- Earlier C# checkpoint: **348 passed**, zero failed/skipped (19 new protocol/client/session cases), plus Shell/Desktop/Widget builds with zero warnings/errors, observed **2026-10-04 10:01:58 +01:00**. This covers malformed success clearing versus a genuinely lost transport acknowledgement. The final host-cache refinement below adds a twentieth case and349 passes. These tests exercise pure request/ack validation, generation/deadline/draft/dismiss/minimize/passive predicates, fake-API client dedup and the production shared session; they do not execute the native `MemoryForm.PresentAsync` UI.
- Effect-free real-launcher forwarding passed at **2026-10-04 10:00:03 +01:00**. No native launch/default switch.
- Final full verification was started in `.local/frontend-verify-20261003` via `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1`, exec session93829. Lint, mypy275 and schema check passed before813 collected tests. Its terminal result is recorded in the final addendum below, not presumed from startup or partial progress.

HTTP coverage: pending has no success event; exact positive/negative acknowledgements; matching duplicates yield one event/outbox row; changed acknowledgement/key conflicts; no payload content/captures/lease/bounds; owner/global/current-project/deleted/version scope checks; malformed/forged origin/authority/visibility/selection/geometry refusal; queue/page bounds; expiry, turn cancellation and host loss; concurrent admission; cancellation while waiting for an atomic write; expiry while waiting prevents success; host/profile/lease/generation conflicts; earlier committed ACK is historical after registry advance; event/outbox failure rollback; remote route403 and actual event sanitation; new-Core invalidation. Companion origin/activation/correlation are tested through the private hub helper only, **not** a connected chooser.

C# coverage: closed public projection excludes private fields; wrong Core/host/lease/record/version/generation/panel/operation/origin/activation rejects; exact visible positive-size highlight anchor required; retained draft/busy/dismiss/minimize/passive/expiry gating; frozen ACK-only reconciliation after transport loss; changed generation cannot reassert positive highlight; uncertain callback not replayed; malformed/wrong-target/missing-event result cannot confirm; shared session opt-in works while model down and prototype/compatibility clients do not register.

Initial test/lint/type checks failed on test fixture SQL/renewal assumptions, draft formatting and an old multiline type-ignore location; these were repaired and rerun. The project-mode assignment now uses an explicit cast after the existing allowlist validation; no project-routing behavior changed. No initial failed result is reported as passing.

## Environment and unproven requirements

Owner Core PID52000/start **2026-09-29 21:49:32**/path `.venv/Scripts/sora.exe` rechecked unchanged at **2026-10-04 10:01:58 +01:00**. No owner migration/settings edit/restart/model reload/voice/avatar/device operation, paid provider call or new native action; no equivalent retry of the previously policy-denied native workflow. Source changes need a later normal restart to become available in that running Core. Isolated tests do not use its `.venv`.

Native exact selection/highlight/current geometry/focus/dismiss/minimize/retained drafts/modal/Quit/layout/DPI/accessibility remains open, as do the model `present_memory` action, actual exposed canonical references, public retrieval/activity IDs, Chat chips and ordinary conversational path. No live2B chooser/model probe occurred. UI host reports are not independent OS attestation. All earlier GUI-0b/1/2/3a/3b acceptance plus scheduler, real graph/design and ordinary-launch/release remain required. Full goal stays active; next source work connects chooser/retrieval/chips, not rebuilding this transport.

## Final regression addendum

**2026-10-04 10:05:02 +01:00:** Same live exec session93829 returned normal terminal exit0. Final Python-source `./scripts/verify.ps1`: **788 Python passed /25 opt-in skipped in94.66s; 8 PWA passed; mypy275/lint/exported-schema check/compile passed**. Python/contracts remained unchanged afterward. This is not native UI, paid-provider, live-model or physical-device acceptance, and does not close GUI-3c.

**2026-10-04 10:10:49 +01:00 final C#-only addendum:** Historical host keys now prune five minutes after expiry rather than permanently filling a continuously renewed host at256 requests. One new component case proves expiration prunes without selection replay. **349 C# passed**, zero failed/skipped; all three final Windows builds have zero warnings/errors. Python source is unchanged from exec93829; this addendum is separately verified, not falsely included in the earlier348 checkpoint or Python run.
