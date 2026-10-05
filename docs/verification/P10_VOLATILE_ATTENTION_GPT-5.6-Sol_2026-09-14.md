# P10.5 Volatile Cursor, Selection and Gesture Verification

- Model: GPT-5.6 Sol
- Completed: 2026-09-14 22:19:22 +01:00 (Europe/London)
- Status: P10.5 complete; P10.1 remains in review; P10.6–P10.7 and overall P10 remain open
- Foundation: Gemini 3.8 Flash's P03A cursor ring buffer, hover/circle prototype and attention contracts; GPT 6 Astra's P10.1 Windows observation boundary; accepted P09 coordinate/marker contracts

## Delivered boundary

P10.5 adds a deliberately volatile local-input path. A capture adapter can submit a bounded batch of cursor samples or one semantic selection through Core, and callers can resolve a hover, click, selection or circle at an explicit timestamp. Raw cursor and selection samples exist only in the runtime-owned in-memory tracker. They are not written to canonical messages, tasks, events, results, memories, traces or SQLite.

Cursor and selection ingress require separate persisted exact-scope `desktop.observe:cursor` and `desktop.observe:selection` grants. Resolution requires `desktop.observe:attention`. Core validates capture age, topology revision, display bounds, selection rectangle containment, optional desktop-target ownership and timestamp ordering before consuming a grant. It rechecks authorization after consumption and before making data available to the tracker.

The cursor ring buffer is bounded by both capacity and an eight-second maximum age. Selection history has its own capacity and maximum age. Old and new sample timestamps remain inspectable only as process memory needed for explicit expiry decisions. Topology changes and runtime shutdown clear both buffers.

Successful recognition returns a short-lived `AttentionTarget` containing owner, device, project and topology scope, a one-pixel cursor point or selection/circle rectangle, confidence and `volatile_local_input` provenance. These targets do not authorize any OS action. P10.6 must still revalidate and resolve conversational references before a later navigation or action grant can be considered.

## Gesture acceptance

Deterministic fixtures establish:

- hover: at least 500 ms within a 15-pixel radius;
- click: a complete left-button press/release within 600 ms and 12 pixels, with long holds rejected;
- selection: the most recent unexpired semantic rectangle at or before the reference time;
- circle: a closed trajectory with bounded duration, velocity, aspect ratio, path length, enclosed area and winding; and
- rejection: diagonal backtracking, an open arc, implausibly fast and slow circles, stale topology, offscreen capture, unordered capture and missing grants.

Capacity eviction, cursor expiry and selection expiry have separate expected statuses/reasons. Rejected stale, offscreen and out-of-order samples do not consume their grants or partially mutate the buffer.

## Privacy acceptance

The route-level fixture submits cursor and selection labels containing unique sentinels, resolves both through the API and then checks every trace payload and the SQLite database bytes. Neither sentinel is present. This proves the tested canonical-storage and trace boundary; it does not claim that an external capture adapter or operating-system diagnostic facility has no independent logs.

## Public contracts and API

Published schemas now include cursor samples/batches, selection samples, resolution requests/results and the extended attention target. The local HTTP and SDK surfaces expose:

- `POST /api/v1/attention/cursor`
- `POST /api/v1/attention/selection`
- `POST /api/v1/attention/resolve`

The existing repository verification script was also corrected to throw when any native `uv` command returns a non-zero exit code. This matters because its schema freshness step previously printed stale schemas but PowerShell continued to pytest and returned success. The P10.5 schemas were regenerated and the corrected gate subsequently passed.

## Commands and results

### Focused attention acceptance

```powershell
.\.venv\Scripts\python.exe -m ruff check src/sora/attention tests/attention
.\.venv\Scripts\python.exe -m pytest tests/attention -q
.\.venv\Scripts\python.exe -m mypy --strict src/sora/attention tests/attention/test_tracking.py
```

Result: Ruff passed, strict mypy passed, and **10 tests passed**.

### Repository gate

```powershell
.\scripts\verify.ps1
```

Result:

- dependency lock sync passed;
- Ruff passed;
- strict mypy passed over 132 source files;
- all published schemas were fresh;
- pytest: **239 passed, 3 skipped in 22.12 seconds**;
- skips were the explicit real-Windows-UIA, real-.NET-transport and packaged-Unity-player opt-ins; and
- compileall passed.

### Native desktop gate

```powershell
.\scripts\verify-desktop.ps1 -Native
```

Result: both .NET projects built with zero warnings/errors and **23 desktop tests passed in 4.81 seconds**.

### Native-enabled full suite

```powershell
$env:SORA_TEST_CSHARP = '1'
$env:SORA_TEST_UIA = '1'
uv run --locked pytest -q
```

Result: **241 passed, 1 skipped in 24.55 seconds**. The only skip was the separately opt-in packaged Unity player already covered by the P09 evidence.

`git diff --check` passed; its output contained only normal Windows CRLF conversion notices.

## Remaining limitations

- P10.1 still needs the live inaccessible/elevated-application matrix.
- This phase supplies authorized Core ingress and deterministic fixtures, not a packaged global Windows cursor hook.
- Speech-time alignment is deferred to P14.5; callers currently provide the reference timestamp.
- Raw samples are intentionally lost on restart, topology change, expiry or shutdown.
- P10.6 must implement reusable and ambiguous conversational references; P10.7 must implement configured real-content navigation.
- Optional jab, wiggle and underline gestures were not implemented.

No pointer movement, click injection, editor mutation, external message, commit, tag or staging action was performed.
