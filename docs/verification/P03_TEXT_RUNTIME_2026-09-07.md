# P03 concurrent text runtime verification

- Date: 2026-09-07
- Completed: 2026-09-07 20:14:27 +01:00 (Europe/London)
- Model: GPT-5.6 Sol
- Environment: Windows 11 Pro 10.0.26200 x64, CPython 3.12.10, uv 0.12.10
- Scope: hermetic deterministic runtime, CLI, scheduling, recovery, faults, reporting, traces, and
  outbox delivery
- Live providers, network APIs, native sessions, provider token streams, and hardware: not
  exercised

## Behavior implemented

- A clearly labeled deterministic mock CLI with one-shot submission, wait, interactive dialogue,
  asynchronous response chunks, and message/task/state inspection plus task wait/cancel/retry.
- Atomic and idempotent message/task/run submission, including stable replay of the original
  acknowledgement after unrelated conversation.
- A bounded FIFO queue, configurable active-task capacity and worker count, persisted leases and
  deadlines, timeout cancellation, terminal wait, supported/unsupported steering, cancellation,
  capped explicit retries, and immutable attempt history.
- Single-process startup recovery that interrupts every persisted prior-process lease, including an
  unexpired lease, without relaunching or replaying its external effect.
- A deterministic provider with delay, failure, rate-limit, malformed-result, disconnect,
  cancellation-race, uncertain-launch, and unavailable modes.
- Independent normalized-result storage and policy-validated patch application. Late completion
  after cancellation is evidence only and cannot mutate facts.
- Grounded reports for queued/routing/reasoning, completed, failed, unavailable, and cancelled work.
- Correlated traces across message, task, run, result, and patch, with redacted context manifests
  and final latency; no raw prompt content is stored in trace fields.
- At-least-once outbox dispatch that advances delivery state only after consumer success.
- Schema migrations through version 4 for submissions, leases, traces, and exact acknowledgement
  linkage.

## Repository verification

```text
.\scripts\verify.ps1
```

Final result:

- Locked dependency synchronization: passed with 18 packages.
- Ruff: passed.
- Strict mypy: passed across 54 Python source/test/script files reported by mypy.
- Generated P01 schema freshness: passed.
- Pytest: 68 tests passed in 3.60 seconds on the final repository-wide run.
- Compileall: passed.

P03-specific tests prove:

- a slow provider does not block streamed deterministic dialogue and pending reports do not invent
  a result;
- capacity exhaustion rejects a second active task without partially persisting it, then admits new
  work after capacity is released;
- duplicate submission creates one task and one provider start while returning the exact original
  acknowledgement;
- a new process reconciles an unexpired orphan lease to interrupted, leaves no lease, and never
  relaunches it;
- normal and cancellation-race results are retained separately from patch application;
- delay, provider failure, rate limit, malformed result, disconnect, unavailability, uncertain
  launch, timeout, supported steering, unsupported steering, ordinary cancellation, and late-result
  cancellation reach their documented outcomes without repeated facts;
- explicit retry creates attempts 1 and 2 under one task and the configured attempt ceiling rejects
  an unbounded third attempt;
- successful tracing contains submission, context, launch, result, patch, and final phases under one
  correlation ID, while secrets and prompt text are absent;
- failed outbox consumption leaves delivery pending and a later successful delivery marks each
  event once.

## Fresh-wheel smoke

The final source was built as both sdist and wheel, installed into a fresh Python 3.12 virtual
environment, and invoked as:

```text
python -m sora --root <fresh-state> --identity-root <repo-identity> \
  --once "Verify the completed Stage 3 installed vertical slice." --wait
```

Observed result:

```text
status=completed
Processed the task deterministically.
schema_version=4
quick_check=ok
tasks=1
runs=1
results=1
facts=1
leases=0
traces=6
```

## Development-machine timing sample

A non-production, in-tree sample submitted 25 deterministic tasks to two workers with 10 ms
injected provider delay. End-to-end completion took 4206.66 ms. Across 200 state inspections after
that workload, latency was p50 3.145 ms, p95 4.870 ms, and max 8.256 ms. This supports the current
local state-query target on this machine only; it is not a provider or multi-user throughput claim.

## Limits

The runtime is single-process and local; it does not yet fence two concurrent Core processes.
Dialogue chunks are deterministic mock output, not a live model's token stream. There is no live
Hermes, Codex, or Antigravity adapter, native provider-session recovery, HTTP/WebSocket API, remote
authentication, multi-client backpressure, workspace execution, or raw personal-content diagnostic
retention. Malformed output is represented by a typed, length-only redacted diagnostic. Queue,
worker, context, deadline, token-budget, and retry limits exist; artifact/output byte enforcement
will be added with adapters that can produce those payloads.
