# SORA

SORA (Spatial Operator for Recursive Antics) is a Windows-local agent runtime under active
development. The current G1 text core provides durable identity/history, bounded context, concurrent
deterministic dialogue and reasoning tasks, validated results/patches, recovery, tracing, and a CLI.

The default provider is a hermetic deterministic mock. Hermes ACP is also available as an explicit
external provider adapter; it requires the Hermes installation and configured credentials. Runtime
state, credentials, local validation artifacts, backups, and provider installations are not committed.

## Bootstrap and verify

On Windows PowerShell, with `uv` available:

```powershell
.\scripts\bootstrap.ps1
.\scripts\verify.ps1
```

Inspect a fresh local runtime with:

```powershell
uv run --locked python -m sora --state
```

Run one deterministic background task and wait for its grounded result:

```powershell
uv run --locked python -m sora --once "Analyze the deterministic fixture." --wait
```

Run through the installed Hermes ACP backend when it is configured:

```powershell
uv run --locked python -m sora --provider hermes --hermes-cwd C:\path\to\isolated\workspace --once "Analyze the repository." --wait
```

The Hermes adapter launches one `hermes acp` process per SORA run, requests a structured JSON
result, and converts facts/memory updates into validated SORA patch proposals. An explicit existing
`--hermes-cwd` assigns its workspace. Hermes retains its native tools and configured MCP integrations
by default, and ACP permission requests select `allow_once`; use `--hermes-deny-approvals` or
`--hermes-skip-configured-mcp` for an explicitly restricted run. SORA does not implement ACP
client-side editor filesystem/terminal methods, which is separate from Hermes' own tools. Native
session resume and cancellation are mapped; steering is not. `hermes acp --check` verifies the local
ACP installation without starting a model run.

Run a bounded read-only Codex task with the cost-sensitive default model:

```powershell
uv run --locked python -m sora --provider codex --codex-cwd C:\path\to\repository --once "Inspect README.md." --wait --task-timeout 120
```

The Codex adapter uses the documented App Server protocol, defaults to GPT-5.6 Luna at low effort,
preserves native thread identity across resume, and maps interruption and activity into SORA's
provider lifecycle. The direct CLI is deliberately read-only. Coding writes require an owned Git
worktree plus a live `GitWorkspaceManager` lease; the adapter rejects unowned `workspace-write` and
all `danger-full-access` runs.

Run an auto-routed coding write in a managed worktree from an explicit base:

```powershell
uv run --locked python -m sora --provider codex --codex-cwd C:\path\to\repository --codex-write-base HEAD --codex-workspace-root C:\path\to\sora-workspaces --once "Edit the requested files and run focused tests." --wait --task-timeout 300
```

The source checkout is not changed. SORA retains the worktree and a review artifact containing the
base, head, status, diff, commands/tests, and uncertainties; it never merges the result automatically.

Start the interactive mock CLI with `uv run --locked python -m sora`. Its commands are:

```text
/task TEXT
/tasks
/state
/messages
/wait TASK_ID
/cancel TASK_ID
/retry TASK_ID
/quit
```

Fault behavior is available for hermetic checks through `--mock-fault`; use `--help` for the
currently supported modes and `--mock-delay` to inject latency. By default, canonical state is kept
under `data/` at the selected `--root` and remains ignored by Git.

The engineering roadmap and verified progress are maintained in
[`SORA_IMPLEMENTATION_PLAN.md`](SORA_IMPLEMENTATION_PLAN.md).

P03 evidence and explicit limitations are recorded in
[`docs/verification/P03_TEXT_RUNTIME_2026-09-07.md`](docs/verification/P03_TEXT_RUNTIME_2026-09-07.md).

Completed P04 Hermes live-adapter evidence and limitations are recorded in
[`docs/verification/P04_HERMES_LIVE_2026-09-08.md`](docs/verification/P04_HERMES_LIVE_2026-09-08.md).
The earlier credential-free implementation record remains at
[`docs/verification/P04_HERMES_ADAPTER_2026-09-07.md`](docs/verification/P04_HERMES_ADAPTER_2026-09-07.md).

Current P05 Codex/App Server and worktree evidence is recorded in
[`docs/verification/P05_CODEX_APP_SERVER_2026-09-08.md`](docs/verification/P05_CODEX_APP_SERVER_2026-09-08.md).
