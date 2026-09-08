# P05 Codex App Server and owned-worktree verification

- Stage: P05 — Codex and safe single-writer coding
- Verification date: 2026-09-08 (Europe/London)
- Model implementing SORA changes: GPT-5.6 Sol
- Live Codex model: GPT-5.6 Luna, low effort
- Status: in progress; P05.1–P05.3 implemented, P05.4 awaits a real SORA Git base
- Git actions in the SORA checkout: no files staged, no commit created
- Progress changelog: `changelog/2026-09-08T143852+0100_P05-PROGRESS_GPT-5.6-Sol.md`

## Supported-interface probe

The active installation reported `codex-cli 0.153.4` and authenticated with ChatGPT. Its documented
App Server stdio interface and locally generated v2 schemas were probed directly.

| Surface | Current interface | SORA mapping/evidence |
|---|---|---|
| Initialization | `initialize`, then `initialized` | Mapped and exercised against the real server and fake conformance server. |
| Authentication | App Server uses the active Codex login/configuration | `codex login status` reported ChatGPT login; no credential value enters SORA output. |
| Sessions | `thread/start`, `thread/resume`, `thread/fork` | Start/resume mapped. Live resume retained native thread `01a0811c-2090-7823-acb7-308e8c38a24f`. Fork is not yet exposed. |
| Turns/events | `turn/start`; streamed turn/item notifications | Completed agent, command, file-change, diff, and turn events are consumed. SORA public `events()` remains false until an `EventEnvelope` stream is implemented. |
| Steering/cancellation | `turn/steer`, `turn/interrupt` | Both mapped. Fake cancellation and a live interrupted Luna turn reconciled as cancelled. |
| Tool restriction | approval policy plus read-only/workspace-write sandbox | Direct CLI is read-only. Writes require an owned worktree and matching live lease. Unexpected approval requests are declined. Danger-full-access is rejected. |
| Model discovery | `model/list` | Real probe returned six visible models. Luna, Terra, Sol, and 5.4 Mini effort ranges matched the local server schema. |
| Structured result | final completed agent message | Prompted JSON is parsed into `NormalizedResult`; proposed facts/memories remain inference-level Core patch proposals. |

Official protocol references:

- [Codex App Server](https://developers.openai.com/codex/app-server/)
- [Codex models](https://developers.openai.com/api/docs/models/all)

## Implementation and conformance

- Added `CodexAppServerProvider` with bounded JSONL framing, a four-MiB line limit for real App
  Server events, initialization, model discovery, native thread start/resume, turn execution,
  steering, interruption, approval decline, process cleanup, and normalized results.
- Added CLI selection with an explicit cwd, GPT-5.6 Luna/low defaults, provider timeout, and
  read-only-only direct operation.
- Added `GitWorkspaceManager`, durable `WorkspaceRecord`, exclusive write leases, resolved-path
  containment, explicit base resolution, detached worktree allocation, source-dirty recording, and
  review artifact capture.
- Codex `workspace-write` now requires the manager-issued record, matching cwd/workspace reference,
  current owner lease, and a lease covering the request deadline.
- Core now atomically persists session-capable providers' native IDs and records the actual provider
  selected by a bounded fallback, preventing a resumed thread from being attributed to the failed
  first-choice backend.
- Conformance covers missing executables, model discovery, start/resume identity, cancellation,
  normalized patches, unsafe sandbox rejection, mismatched workspace authority, source preservation,
  exclusive writers, and exact diff capture.

## Live read-only and resume acceptance

An ignored two-file Git fixture was inspected with GPT-5.6 Luna at low effort and App Server
`read-only` sandboxing.

| Check | Result |
|---|---|
| First task | read `README.md` with one logical command and reported marker `SORA-P05-LUNA-READONLY` |
| Changes | none reported; Git status before and after was identical |
| Native session | `01a0811c-2090-7823-acb7-308e8c38a24f` |
| Resume | same native thread ID; returned the prior marker without a command |
| Live cancellation | thread `01a08124-853a-7e83-9af2-1545010f95c2` interrupted and normalized as `cancelled` |

The same read-only task then ran through `SoraRuntime`, completed with marker
`SORA-P05-LUNA-READONLY`, and atomically persisted native thread
`01a0812f-541e-7b90-b58c-f67008d43594` in both the agent-session row and run payload. The database
returned `PRAGMA quick_check=ok`, held zero runtime leases after completion, and emitted a
`session.attached` trace without persisting credentials.

An earlier full-checkout Luna probe was intentionally not accepted: transport and command events
worked, but the broad task exceeded its 120-second bound. That run exposed and led to the four-MiB
JSONL limit fix. The isolated scenario above is the bounded acceptance evidence.

## Live isolated-write evidence

A separate ignored committed fixture was used because the real SORA checkout has no commit/`HEAD`.
The manager allocated detached worktree `p05-live-write` from explicit base
`aef95475c646b8abee27c4a54d42c1a3f9888bf8`, with an exclusive `p05-acceptance` lease. Live Luna
changed only `src/sora_fixture.py` from `return "before"` to `return "after"`.

- The source fixture remained unchanged.
- The worktree status contained only the requested tracked change when the artifact was captured.
- Captured head equaled the base because Codex correctly did not commit.
- The captured binary-capable Git diff showed the exact one-line change.
- Codex reported its read/edit commands and truthfully warned that neither `python` nor `py` was
  available inside its sandbox, so provider-side verification was unknown.
- SORA then ran the fixture with its known `.venv` interpreter and observed
  `fixture verification passed`; this is separate host-side evidence.
- The write lease was released while the worktree and review evidence were retained.

## Remaining P05 boundary

P05.4 and the overall stage remain open. The current SORA repository has zero commits and every
project file is untracked, so Git cannot allocate a worktree from an honest SORA base revision. SORA
will not create an initial commit, stage the user's files, or substitute a fabricated base without
explicit authorization. Once a real base exists, repeat the bounded write/test/artifact matrix on an
owned full-SORA worktree, then record the completion timestamp and create the required
`P05_GPT-5.6-Sol` completion changelog.

## Current repository verification

- `scripts/verify.ps1`: clean Ruff, strict mypy across 84 source files, and **139 passed in
  8.35s** with no warnings.
- Fresh sdist and wheel: built successfully into ignored validation storage.
- Fresh Python 3.12 wheel environment: Codex provider and Git workspace manager imports passed.
- The Antigravity cancellation cleanup warning exposed by the first full run was corrected by
  letting the active `communicate()` drain subprocess pipes before teardown; its focused suite then
  passed with unraisable warnings promoted to errors.
