# Foreground continuity / low-cost-model verification

Author: **GPT-6 Astra**. Slice completed **2026-10-02 17:48:59 +01:00**.
Scope: W4 and the native-event foundation of passive perception, not all frontend acceptance.

## Implemented behavior

`src/sora/desktop/foreground.py` keeps only transient process/window identity. Its native thread
uses foreground and desktop-switch WinEvents; it does not read UIA text, capture pixels, focus
windows, inject input or invoke the model. It requires the static desktop-observe switch and
configured native bridge. Core starts/stops it independently of Unity or renderer topology.

An application-to-SoraDesktop/SoraWidget/Sora focus transition preserves the recent application
with a focus-lost timestamp. The hint expires after five minutes. Native desktop-switch events,
known lock-process observations, setting changes, watcher failure and shutdown invalidate it.
The implementation's SORA-process exclusion is a basename heuristic for context, not a trusted
identity or authorization check. Browser/PWA tab handoff is not supported by that heuristic.

Core snapshots the hint at turn entry; subsequent focus changes cannot silently retarget that
turn. `list_windows` only returns a recent target when fresh PID/HWND/process-start identity
matches. The model then uses `inspect_window` for current text/selection. Closed/reused windows
cannot inherit the hint. UIA providers can still change or clear a selection when focus leaves;
the hint does not preserve a historical selection's contents.

Delivery is bounded and coalesced, preserving the last application before a SORA event and any
intervening reset. Settings generations reject delayed callbacks across OFF/ON and failed starts.
Watcher start/stop is serialized; a failed stop does not admit a second source. Live status checks
discard memory if its thread is no longer running.

## Evidence

| Check | Actual result | Boundary |
|---|---|---|
| Full final verification | 522 Python passed / 16 opt-in skipped in 71.70s; 7 PWA checks; Ruff, mypy 224 files, schema freshness and compile checks passed | Not a Unity, voice or full GUI result |
| Native WinEvent smoke | 1 passed in 0.28s | Initial seed/stop only; no real lock/unlock simulation |
| Unit lifecycle/ref checks | Handoff, five-minute expiry, long-active-window timestamp, PID reuse, 1,000-event coalescing, reset ordering, OFF/ON callbacks, failed start/retry, dead watcher, disabled startup | Deterministic fixtures, not a cross-application coverage matrix |
| Native UIA + real local model | Correctly chose recent reference, inspected selection and returned `bef`; no click or text mutation | Prior application identity seeded by the test; inventory deliberately restricted to the owned fixture |
| Local answer latency | 30.89s before / 9.23s after explicitly disabling default thinking; read loops 7.20s / 7.39s | Single controlled comparisons, no general performance guarantee |
| Settings GUI | Companion access visible first; header names `gemma-4-E2B-it-IQ4_XS.gguf` | Read-only review; no security/privacy toggle manipulation |
| Unnamed-window GUI prompt | Submitted after activating selected fixture then SORA; no verified answer before deadline | Acceptance remains open; later UI recovery failed with `coordinate input geometry is unavailable` |
| Cleanup | Owned QA PIDs absent, ports 18784/18785 clear | Other user processes untouched; logs/QA state preserved |

Model: local `gemma-4-E2B-it-IQ4_XS.gguf`, matching `mmproj-F16.gguf`, managed `C:/llama.cpp/llama-server.exe`,
8192 context, GPU layers auto. No paid provider. The GUI failure's model log showed roughly
9–11 generated tokens/second and a cancellation. That log proves slow/cancelled inference,
not a particular GPU-contention cause or successful target resolution.

The full-answer controlled test first returned `The selected text in the application was "bef".`
in 30.89 seconds. After the local thinking-default change it returned
`The selected text in the "SORA UIA acceptance fixture" window was "bef".` in 9.23 seconds.
Both used real native fixture contents. A repeated read was bounded by the existing loop guard.

The safe timeout error now identifies a conversation deadline separately from model unavailability,
suggests checking the transcript before retrying, and points to Dialogue timeout in Settings.
Native/file observations and backend exception details are not echoed into this error.

## Reproduction

From the repository, with no duplicate acceptance fixture open:

```powershell
./scripts/verify.ps1
$env:SORA_TEST_FOREGROUND = '1'
uv run --locked pytest tests/desktop/test_foreground.py::test_native_foreground_seed_and_stop -q
Remove-Item Env:SORA_TEST_FOREGROUND
$env:SORA_TEST_FOREGROUND_MODEL_CONFIG = 'C:\Users\oscar\Desktop\SORA\.local\native-read-qa-20261002\llama.json'
uv run --locked pytest tests/desktop/test_foreground.py::test_live_recent_reference_routes_selection -q -s
Remove-Item Env:SORA_TEST_FOREGROUND_MODEL_CONFIG
```

The model test creates its own temporary state, native fixture and dynamically allocated model
port, supplies an in-memory random server credential, and closes owned children in `finally`.
Its output is limited to the synthetic fixture observation and answer. GUI QA used the existing
isolated `.local/native-read-qa-20261002` state, not personal SORA history/settings.

## Required next work (not completed)

1. Clean end-to-end GUI rerun of unnamed prior-application selection after the latency fix;
   widget handoff and real editor coverage, including focus-dependent selections.
2. Static native-only/image-on-prompt/adaptive modes in shared JSON/GUI; lightweight prompt-time
   context and optional change-aware image intervals, model scheduling/priority and no backlog.
3. Full pause/lock/conversation cancellation behavior. Current desktop-switch invalidation
   clears this identity hint; it does not prove that in-flight inference or all effects pause.
4. Better user-visible native readiness/reading/cancel/provenance UX and full startup/restart
   parity. The new watcher status is exposed by Core; no new GUI status panel is claimed.
5. Existing W4 gaps: targeted visual fallback, broader file formats, mixed read/effect orchestration,
   freshness/topology/application coverage, plus every remaining W1/W2/W3/W5/W6 tracker row.
