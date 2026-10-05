# Adaptive perception — implementation and acceptance evidence

Contributor: **GPT-6 Astra**. Slice completed **2026-10-02 23:25:49 +01:00**.
Full frontend goal remains active. This record distinguishes Settings presentation, native/model
runtime testing, mocked lifecycle checks and still-unverified user-side behavior.

## Current behavior

Settings offers native-only (default), image-on-prompt and adaptive. Adaptive uses the configured
refresh interval and one background job. Captures are native recent-application window images,
not a whole desktop fallback. SHA-256 plus PID/HWND/process-start identity determines whether
another interpretation is necessary. Unchanged captures refresh the verification timestamp, not
the interpretation timestamp. Expired or different-application context is not injected into chat.

One bounded 1,600-character summary is kept in memory. Background interpretation appends no chat
turn, retains no raw frame in Core's desktop frame store, and calls no read/action/memory/delegation
or presentation dispatch. A foreground local prompt can receive the matching summary with both
times and an untrusted-data label; it is not a fresh targeted read or authority for effects.
Without valid cached context, adaptive prompts use the normal window-image path. Native targeted
text/selection remains available and preferable. Remote sessions receive neither ambient summary
nor automatic local images.

Foreground chat/voice model sessions close background admission synchronously, cancel the active
background job and wait up to two seconds for its transport to drain. If it has not drained, Core
returns a retry error rather than overlapping inference. The job generation changes before
cancellation, so a cancellation-resistant late response cannot publish after that deadline.
Background interpretation is bounded by min(20s, dialogue timeout). Missed timer ticks do not queue.
Live interval increases/decreases reschedule the timer rather than execute an old pending tick.

Pause/access/perception edits, provider replacement, changed application identity, desktop/lock
invalidation, dead foreground watcher and shutdown invalidate/cancel background context. This
does not prove interruption of every foreground turn, media pipeline or desktop effect.

## Evidence

| Check | Result | Scope |
|---|---|---|
| Final full verification | 538 passed / 18 opt-in skipped in 85.02s; 7 PWA; Ruff/mypy 227 files/schema/compile checks; exit 0 | No Unity, actual voice device or every GUI capability acceptance |
| C# and builds | 36 tests passed; full app/widget zero-warning builds | Desktop client parsing/build compatibility |
| Scheduler/lifecycle tests | Change detection, identity/start-time reuse, TTL, timer/no backlog, interval edits, preemption, two-second stubborn cancellation, pause/lock/remote runtime behavior | Deterministic fixtures; lock invalidation callback is not real OS lock/unlock |
| Actual native/model timer path | 1 passed in 25.43s; context ready after 8.64s (5s initial delay; refresh 3.625s), unchanged check skipped inference | Owned synthetic window, seeded identity; actual PrintWindow/local-model inference |
| Cached-context foreground response | `before`, with background capture/verification timestamps and native read evidence | Runtime path; model may combine cached interpretation with fresh native text |
| Actual model transport preemption | Background cancelled; foreground answered `before` in 3.22s, using prompt-image fallback | Real model/HTTP cancellation and recovery, not a general latency benchmark |
| GUI | Mode list showed all three choices; interval 30.0/max age 90.0/Immediate; final status wrapped visibly | Read-only review; no mode/access toggle, adaptive chat or save/restart GUI acceptance claimed |
| Cleanup | Owned QA processes absent, ports 18784/18785 clear; isolated logs/state retained | Owner's SORA state/history and other processes untouched |

GUI review used `.local/adaptive-qa-20261002`, separate from normal state. The first screenshot of
the occluded app was unusable; activating the exact returned SORA window produced correct app
screenshots. The mode dropdown was opened then closed with Escape, with native-only unchanged.
The final app rebuild fixed clipped status lines through width-constrained wrapping. This also
closes the prior prompt-perception slice's post-polish Settings layout recheck.

The native integration test restricts inventory/model inputs to its own fixture, allocates a new
model port and random in-memory credential, and closes children in `finally`. It verifies zero
fixture clicks/text changes, no chat records from background refresh, and no stored desktop frames.
Local model: Gemma 4 E2B IQ4_XS plus matching F16 projector and existing managed llama.cpp. No paid
provider, weight download or unrelated private window content was used for the model test.

An initial broad-description test returned a sensible application description but did not include
the field word expected by its assertion. The test question was corrected to explicitly ask for
that word; the final exact-word tests passed. The visual summary also guessed the meaning of
masked dots, illustrating why interpretations remain untrusted, not verified UI semantics.

## Reproduction

```powershell
./scripts/verify.ps1
dotnet test clients/csharp_tests/csharp_tests.csproj --no-restore
$env:SORA_TEST_PERCEPTION_MODEL_CONFIG = 'C:\Users\oscar\Desktop\SORA\.local\native-read-qa-20261002\llama.json'
try {
    uv run --locked pytest tests/runtime/test_adaptive_perception.py::test_native_adaptive_context_with_local_model -q -s
} finally {
    Remove-Item Env:SORA_TEST_PERCEPTION_MODEL_CONFIG
}
```

Requires the existing local model/projector and built native helpers. Settings version 5 migrates
valid v2/v3/v4 stores with original backups, preserving access/mode/pause and adding timing defaults.
The normal default remains native-only; adaptive does not turn itself on after an upgrade.

## Remaining acceptance

Full adaptive/image-on-prompt GUI chat and save/restart acceptance; actual Windows lock/unlock and
cross-editor/widget cases; full foreground cancellation; voice sharing of read/action orchestration;
semantic/visual action targeting; richer file adapters; normal startup/avatar lifecycle, catalogue,
delegation and every other row of the [active tracker](FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md).
No W4, W1 or overall-goal completion is inferred from this slice.
