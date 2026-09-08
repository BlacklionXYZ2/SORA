# P05 Codex App Server and owned-worktree verification

- Stage: P05 — Codex and safe single-writer coding
- Verification date: 2026-09-08 (Europe/London)
- Model implementing SORA changes: GPT-5.6 Sol
- Live Codex model: GPT-5.6 Luna, low effort
- Completed: 2026-09-08 15:17:15 +01:00 (Europe/London)
- Status: complete; P05.1–P05.4 accepted
- Git actions in the SORA checkout: authorized baseline commits `a4b7118` and `f370082`; live acceptance artifact not staged, committed, or merged
- Completion changelog: `changelog/2026-09-08T151715+0100_P05_GPT-5.6-Sol.md`

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
- Added `CodingRunArtifact`, combining Git base/head/status/files/diff with the provider outcome,
  commands, verification commands, files read/changed, warnings, and uncertainties in one durable
  review record.
- Codex `workspace-write` now requires the manager-issued record, matching cwd/workspace reference,
  current owner lease, and a lease covering the request deadline.
- Integrated P06 coding writes with per-run worktree allocation, concrete Codex provider binding,
  artifact capture before result acceptance, and lease release in terminal cleanup. Coding writes
  have no provider fallback; missing isolation or a non-Codex write provider fails closed.
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

## Full-SORA P05.4 acceptance

The user's request to finish P05 authorized the required repository baseline. Commit `a4b7118`
established the combined SORA baseline containing the already completed P03A work and Gemini's P06
implementation; commit `f370082b89924da37b832fec59b78e1ab4b9b52c` added the final routing
classification/fail-closed corrections and was the explicit clean base for acceptance.

P06 routed task `task-44bf8027-4fc8-4581-a32e-7f96be73fd79` as `coding_write` to
`codex-app-server` with no fallback. `SoraRuntime` allocated
`workspace-run-33a4d057-0542-46de-ae49-7c88b70b13cb`, bound GPT-5.6 Luna at low effort to that
worktree, and persisted native thread `01a08150-e844-7250-adf0-451e9690328e`.

The durable artifact has SHA-256
`6c1eff5700fc6f1c919e97434d73a44dc55fd12e32845035ab8ba699b68b2ef9` and records:

- requested/resolved base `f370082` / `f370082b89924da37b832fec59b78e1ab4b9b52c`;
- unchanged head because the provider correctly did not commit;
- exactly `src/sora/providers/codex.py` and `tests/providers/test_codex.py` as changed tracked files;
- the complete diff adding `display_name="Cody"` and its test assertion;
- provider commands, verification attempts, files read/changed, warnings, and the explicit
  uncertainty that its sandbox could not launch the project's configured interpreter.

The source checkout remained clean and unchanged. The artifact was captured before result
acceptance, its reference was attached to the normalized result, and both the workspace lease and
runtime lease were released while the review worktree was retained. SQLite `PRAGMA quick_check`
returned `ok`. Host-side verification then set `PYTHONPATH` to that exact worktree and passed the
entire Codex provider module: **6 passed in 0.66s**. The live changes remain unmerged for explicit
review.

## Current repository verification

- `scripts/verify.ps1`: clean Ruff, strict mypy across 85 source files, and **145 passed in
  9.08s** with no warnings.
- Fresh sdist and wheel: built successfully into ignored validation storage.
- Fresh Python 3.12 wheel environment: Codex, Antigravity, routing, runtime, workspace manager, and
  `CodingRunArtifact` imports passed together.
- The Antigravity cancellation cleanup warning exposed by the first full run was corrected by
  letting the active `communicate()` drain subprocess pipes before teardown; its focused suite then
  passed with unraisable warnings promoted to errors.
