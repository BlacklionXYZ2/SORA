# P01 contracts and policy verification

- Date: 2026-09-07
- Model: GPT-5.6 Sol
- Environment: Windows 10.0.26200 x64, CPython 3.12.10, uv 0.12.10
- Scope: hermetic contracts, fixtures, policy, packaging, and generated-schema verification
- Live providers, persistence, API, desktop actions, and hardware: not exercised and not claimed

## Behavior implemented

P01 establishes strict JSON contract version `1.0` for task, run, session, provider capabilities and
requests, normalized results/errors, proposed patches, events, capability requests/grants, and
approvals. Models are immutable, reject unknown fields, validate aware timestamps and lifecycle
conditions, and produce committed JSON Schemas.

Task, run, and native provider session have distinct identities. Task retry is a recorded terminal to
queued transition; terminal runs remain terminal and a retry must create another run. `reasoning` and
`working` have documented meanings. Task, run, and approval transitions use explicit allowlists.

Patch preflight distinguishes applicable, duplicate-idempotency, and entity-version conflict
outcomes without mutating state. Event handling distinguishes first, contiguous, duplicate,
cross-stream, regression, and gap cases. Provider capability checks return typed unsupported errors;
uncertain launch and lost session remain typed inspectable failures.

Capability authorization is scoped by owner, device, project, operation, resource, time window,
status, and use count. Path grants require absolute paths and use resolved containment instead of
string-prefix matching. Untrusted content is absent from the authority input and extra fields fail
closed. Approval decisions are terminal and late decisions become expired. Structured audit fields
are recursively redacted before logging.

## Contract artifacts

- 11 generated JSON Schemas under `contracts/schema/v1`.
- 11 valid shared examples under `contracts/examples/v1/valid`.
- Scenario fixtures for malformed output, stale patches, duplicate delivery, uncertain launch, lost
  sessions, and backend-native field leakage.
- `contracts/README.md` compatibility, retry, cancellation, ordering, idempotency, and authority
  rules.
- ADR 0002 records the versioning and compatibility decision and reversal path.

## Verification commands and results

```text
.\scripts\verify.ps1
```

Result:

- Locked dependency synchronization: passed with 18 packages.
- Ruff lint: passed.
- Strict mypy: passed across 28 Python source/test/script files.
- Generated-schema freshness check: passed.
- Pytest: 35 tests passed.
- Python compileall: passed.

The tests cover:

- round trips for all 11 published record/envelope types;
- rejection of offset-naive timestamps, malformed completed results, illegal transitions, and
  backend-specific fields;
- task/run/session separation and terminal-run preservation on task retry;
- cancellation race states, uncertain launch, lost session, and unsupported methods;
- applicable, duplicate, and stale/conflicting patches;
- first/next/duplicate event delivery and explicit event-gap failure;
- exact tool scope, path sibling-prefix escape, approval expiry, and terminal approvals;
- injected text failing to enter or widen authority inputs;
- fixture API keys/tokens absent from captured audit logs.

Additional artifact checks:

```text
uv run --locked python scripts/export-contracts.py --check
RESULT: PASS

Parse every contracts/**/*.json with ConvertFrom-Json
RESULT: PASS — 28 JSON files valid, including 11 schemas.

Search public schemas for Hermes, Codex, or Antigravity names
RESULT: PASS — no backend-specific names present.

uv build --out-dir .local\p01-dist
RESULT: PASS — source distribution and wheel built.

Install wheel into fresh .local\p01-wheel-venv and decode provider-request.json
RESULT: PASS — wheel_contract=1.0:run-001.
```

## Limits and next work

These are validation contracts and pure policy decisions, not persistence or an authorization
service. P02 must persist identities, versions, idempotency keys, grants, approvals, results, patches,
and transactional outbox events; it must recheck patch preconditions and capability state inside the
commit transaction. Use-count consumption, revocation races, migration, and secret storage also
belong to that durable boundary.

Provider contracts do not establish that Hermes, Codex, or Antigravity support a particular method.
Each live adapter phase must publish independently verified capabilities and translate native data at
the boundary. Event replay transport, API authentication, workspace isolation, and desktop action
postconditions remain later stages.
