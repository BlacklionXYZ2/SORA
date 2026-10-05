# W4 adaptive perception scheduling — GPT-6.1 Sol

Slice completed **2026-10-02 23:25:49 +01:00** (Europe/London).
Status: **implemented; native/local-model runtime path and Settings presentation verified**.
W4/passive perception and the full frontend goal remain **in progress**.

## Implemented changes

- Added adaptive mode alongside native-only and image-on-prompt. The default remains native-only;
  background image processing is opt-in. Settings exposes refresh interval (30s default, 5–300s)
  and maximum context age (90s default, 5–600s), both live-applied.
- Added a single replaceable refresh slot with no backlog. Native capture stays limited to the
  recent validated application. Unchanged PNG bytes and unchanged process/window identity reuse
  the interpretation while recording a new image-verification timestamp; changed images invoke
  the model. Retained context is one bounded, transient summary, not saved frames or chat turns.
- Made foreground chat and voice model sessions cancel background work before admission. A
  two-second cancellation-drain limit returns an error instead of overlapping inference if the
  background transport does not cooperate. Generation checks reject late replies, including
  replies after that drain deadline. Background model calls have a maximum 20-second deadline.
- Cleared context/cancelled refresh on settings change, pause, application identity changes,
  desktop/lock invalidation, model-provider replacement, watcher failure and shutdown.
- Supplied matching recent background summaries to local prompts with interpretation/verification
  times and explicit untrusted/interval-context labels. Missing/expired context uses prompt images
  instead. Remote requests inherit no ambient context. Background interpretation invokes no
  tools, memories, agent delegation, animation or desktop effects.
- Introduced settings version 5 with original-preserving v2/v3/v4 migration. Existing access,
  mode and pause choices remain intact. Updated generated schemas, example and Windows-client
  parsing; malformed/incomplete current flags still fail closed.
- Added scheduler, migration, cache identity/TTL, timer, live-interval-edit, preemption, stubborn
  cancellation and runtime-revocation tests, plus opt-in actual native/model integration.
- Exposed bounded refresh state/counters/duration without private summary text in Settings status.
  GUI inspection found status clipping at normal width; added width-constrained wrapping and
  verified the rebuilt result visually. Updated runbooks, plan and tracker additively.

## Verification

- Final `scripts/verify.ps1`: **538 Python passed, 18 opt-in skipped**, 85.02s; **7 PWA checks**.
  Ruff, mypy (227 source files), contract freshness and compile checks passed; exit code 0.
- **36 C# tests passed**. Full app and widget builds: zero warnings/errors. Final full-app layout
  rebuild and Computer Use review showed fully wrapped status text, with no lost warning text.
- Read-only GUI review showed native-only/image-on-prompt/adaptive choices, interval 30.0,
  maximum age 90.0 and Immediate badges. No security/privacy control or mode was changed via GUI.
- Final opt-in native/local-model timer/runtime test: **1 passed in 25.43s**. The timer produced
  fixture context after 8.64s (including initial 5s wait; refresh 3.625s), skipped a second model
  interpretation for unchanged pixels, and SORA answered `before` with source timestamps.
- Actual HTTP/model foreground preemption then answered `before` in **3.22s**, with the cancelled
  background task unable to publish. Fixture click/text-change counts stayed zero; background
  refresh created no conversation records or stored desktop frames.
- Test model: local `gemma-4-E2B-it-IQ4_XS.gguf` with matching `mmproj-F16.gguf`, managed llama.cpp.
  No paid providers, downloads or owner-data edits. Owned QA processes stopped; ports 18784/18785
  clear; isolated state/logs retained.

## Open boundaries

Native/model testing seeds the prior fixture identity and restricts native inventory to that owned
window. It is not full GUI adaptive-mode acceptance, real lock/unlock or cross-editor coverage.
The 30s default is conservative/configurable, not a GPU performance recommendation or benchmark.
Pixel equality is not semantic change detection; blinking/animation can cause extra interpretation.
Interpretations remain fallible: the 2B model described masked dots imprecisely, so summaries are
never action authority. Full foreground cancellation, shared voice read/action orchestration,
normal restart, image/adaptive GUI chat acceptance and all other frontend workstreams remain open.

[Detailed evidence](../docs/verification/W4_ADAPTIVE_PERCEPTION_GPT-6-Astra_2026-10-02.md).
