# W4 foreground continuity and local-reply latency — GPT-6.1 Sol

Completed implementation/verification slice: **2026-10-02 17:48:59 +01:00** (Europe/London).
Status: **implemented; native/model components verified; full GUI handoff acceptance open**.
W4, passive perception and the overall frontend goal remain **in progress**.

## Changes implemented

- Added a native foreground/desktop-switch WinEvent watcher and volatile last-non-SORA
  application identity, independent of avatar rendering, screenshots and model inference.
  Stored metadata is PID, HWND, process start time/name and observation time, not window text.
- Preserved application-to-SORA handoff, including a long foreground session and coalesced
  event storms. Five-minute expiry, desktop-switch invalidation, settings-epoch/generation
  checks, shutdown cleanup and failed-start callback rejection prevent stale reuse.
- Added watcher health reporting and discarded context when the native thread is no longer
  live. A failed stop cannot launch a duplicate watcher.
- Snapshotted the recent application at conversation entry, revalidated it against fresh
  native inventory, and exposed its opaque reference to the existing small-model read schema.
  Text/selection still require a fresh UIA inspection; the hint grants no action authority.
- Added distinct safe `DIALOGUE_TIMEOUT` API errors. Provider timeouts no longer trigger a
  malformed-read-call repair/retry. Existing clients already display the returned explanation.
- Explicitly disabled server-default extended thinking for ordinary loopback-model replies,
  including image replies; preserved the explicit memory-rationale opt-in and ordinary hosted
  provider request compatibility.
- Added foreground lifecycle/routing tests, a controlled opt-in native/local-model test,
  timeout/compatibility tests and updated the local tryout guide and alignment tracker.

## Verification

- Final `scripts/verify.ps1`: **522 passed, 16 opt-in skipped**, 71.70 seconds; **7 PWA checks**;
  Ruff, mypy (224 source files), contract freshness and compile checks passed.
- Native Windows hook seed/stop: **1 passed**, 0.28 seconds, after final watcher changes.
- Controlled local Gemma 4 E2B IQ4_XS with matching F16 projector: recent reference resolved to
  real fixture UIA selection `bef`; zero fixture clicks/text changes. Final answer:
  `The selected text in the "SORA UIA acceptance fixture" window was "bef".`
- Same controlled test measured full read/answer time **30.89s before / 9.23s after** the local
  thinking-default fix (read loops 7.20s / 7.39s). These are individual runs, not a general benchmark.
- GUI review verified Companion access first in Settings and the actual GGUF model label.
  The unnamed-window GUI read hit its deadline under slower inference; later computer-use
  recovery failed with `coordinate input geometry is unavailable`. No successful full GUI
  handoff is claimed. The controlled model test seeds the prior identity and is not its substitute.
- One regression initially failed because the image-request fixture expected no template
  options; its expected request now explicitly checks the intended non-thinking local mode.
  Final full verification is green.
- Closed only owned isolated QA app/fixture/Core/model processes; QA ports 18784/18785 and
  recorded owned PIDs were absent on cleanup. Preserved QA evidence and personal state.
  No paid specialist request, commit, or deletion of user files.

Details and open acceptance gates:
[foreground verification](../docs/verification/W4_FOREGROUND_CONTEXT_GPT-6-Astra_2026-10-02.md).
