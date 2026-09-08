# P04 Hermes adapter verification

> Historical implementation record. P04's bounded live gate was subsequently completed and the
> adapter hardened on 2026-09-08; see
> [`P04_HERMES_LIVE_2026-09-08.md`](P04_HERMES_LIVE_2026-09-08.md).
> That day's later trust-policy amendment supersedes this historical file's permission-denial and
> no-tool defaults: Hermes-native tools/configured MCP are enabled with `allow_once` approvals.

- Date: 2026-09-07
- Model: GPT-5.6 Luna
- Environment: Windows 11, CPython 3.12.10, uv locked environment
- Scope: Hermes ACP provider boundary, normalized results, patch proposals, lifecycle cleanup, and CLI selection

## Implemented behavior

- `HermesACPProvider` launches the configured `hermes acp` command through Windows-compatible asyncio subprocess pipes.
- ACP `initialize`, `session/new`, and `session/prompt` requests are handled with newline-delimited JSON-RPC.
- `session/update` agent message chunks are collected and normalized.
- Hermes JSON and fenced JSON responses are converted to SORA `NormalizedResult` records.
- Hermes facts and memory updates become validated SORA `PatchEnvelope` proposals; Core remains responsible for applying them.
- Provider launch failures, lost sessions, malformed output, cancellation, and process cleanup remain outside Core-specific Hermes branches.
- The CLI now supports `--provider deterministic|hermes`, `--hermes-command`, `--hermes-cwd`, and repeated `--hermes-arg` options.
- ACP permission requests are denied by default. Resume, steering, and grant-aware tool restrictions are explicitly not claimed.

## Verification

```text
uv run --locked python -m pytest -q
71 passed

uv run --locked ruff check src tests
All checks passed

uv run --locked mypy src tests
Success: no issues found in 55 source files

hermes acp --check
Hermes ACP check OK
```

The adapter tests include a local fake ACP process, so the suite verifies the actual subprocess/JSON-RPC lifecycle without credentials or external model calls.

## Live-provider status

No live Hermes task was launched during this stage. A live task would invoke the configured external model and could expose Hermes tools, so it requires an intentional bounded acceptance run with explicit credentials, workspace, and permission policy. P04.1 protocol verification and P04.2 adapter/conformance work are implemented; P04.3 live scenarios remain open.

## Limits

The adapter uses one Hermes process per SORA run. Native ACP session persistence/resume, steering, capability-grant translation, tool-result normalization, and live event persistence remain future work. The default deterministic provider is unchanged.
