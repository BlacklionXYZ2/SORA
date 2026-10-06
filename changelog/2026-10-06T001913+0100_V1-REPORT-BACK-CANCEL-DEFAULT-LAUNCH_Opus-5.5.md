# V1: task report-back, whole-tree cancel on Windows, native app as default launch

Model name: **Opus 5.5**. Checkpoint **2026-10-06 00:19:13 +01:00**, Europe/London. Status:
**implemented. Component-tested, plus live checks on the owner's machine through an isolated
Core.** This moves [V1.md](../V1.md) steps 1, 6 and 7 forward. No step is closed; closing V1
needs the owner's full acceptance run.

## Verification of the pulled work first

The four 2026-10-05 changelogs were written in a Linux container. On the owner's Windows machine,
before any change: ruff clean, `mypy --strict` clean (294 files), schema check clean, **962
passed / 25 skipped / 4 strict expected failures**, C# 369/369, three zero-warning builds, PWA 8/8.
The 8 Python and 16 C# failures that the container reported do not occur on Windows. Spot checks
matched the claims: the Claude and Antigravity full-access defaults with their opt-out flags, and
private context reaching hosted agents.

## Changes

- **SORA reports finished work in conversation (step 6).**
  - New `src/sora/runtime/task_reports.py` (`TaskReporter`). When a run ends `completed`, `failed`
    or `cancelled`, it posts one assistant message.
  - Her local model phrases the message from Core-verified facts only, with a 45 s limit. A
    factual line ("Claude finished: …" or "Claude's task was cancelled.") is always kept. If the
    model is unavailable, the factual line is posted alone.
  - The message emits `message.finalized`, so the native app's existing sync shows it with no
    client change.
  - Switch: `RuntimeConfig.report_task_outcomes`. It is off by default, so embedded and test
    runtimes keep exact conversations, and the launcher turns it on.
- **Cancel now really stops the agent on Windows (steps 6 and 10).**
  - Found live: cancelling a Claude task killed the npm `claude.CMD` wrapper, but **the real
    `claude.exe` kept running** and the task was recorded as `failed`.
  - New `src/sora/providers/process_tree.py` (`OwnedProcess`). Each agent run is created
    suspended, assigned to its own kill-on-close Windows job, then resumed. Cancel and timeout
    stop the whole tree, and "writer stopped" is reported only once the job is empty.
  - Used by Claude, Antigravity, Hermes, custom ACP agents and Codex.
  - **Codex's earlier writer-job bootstrap did not contain real agents under Microsoft Store
    Python.** Store Python runs in a job that lets non-packaged children (`cmd.exe`, `node`)
    break away. The existing test only passed because its child was Store Python itself. Codex
    now uses the same suspended start.
  - `windows_job.job_active_processes()` was added for tests.
- **A requested cancellation is recorded as cancelled.** When an adapter raises `CANCELLED` for a
  run whose status is `cancel_requested`, the runtime records `cancelled` instead of `failed`. An
  unrequested `CANCELLED` error still counts as a failure.
- **The native app is the default launch (step 1, GUI-6a).**
  - `Start-SORA.ps1` and `scripts/start-full-sora.ps1` now default to `-Client Shell`.
  - A `-NoClient` start without an explicit client keeps the headless Core path.
  - The launcher verifier and the PowerShell parser pass.
- **Docs.**
  - `V1.md`: the presence, brain and agents rows, plus a new "How to run the acceptance test"
    guide.
  - The README and two runbooks now describe the new default.
  - Roadmap §4.0: the GUI-6 row.

## Live checks on the owner's machine (isolated Core on port 18990, own state folder)

- **Claude:** `claude -p` launched through the npm shim and returned a structured result
  (`completed`, session captured). A delegated task through Core's real API completed in 22 s,
  and the report appeared in the conversation.
- **Cancel, before the fix:** the task ended `failed` and the real `claude.exe` kept running. I
  stopped that process.
- **Cancel, after the fix:** the task ended `cancelled` within 1 s, no headless `claude.exe` was
  left, and the report was posted.
- **Custom agent "Pip"** (OpenAI-compatible, LM Studio's already-loaded Gemma 4 12B on port 1234,
  configured in the test Core's settings): it completed in 16 s and was reported as "Pip
  finished: …". A project folder is correctly refused for a chat-only agent.
- **All four agent CLIs** (Claude, Aggie, Cody, Hermes) launch from Python on Windows.
- The owner's own Core, LM Studio and Hermes servers kept running throughout.

## Not done, and why

- **Nothing that needs the GPU was run:**
  - E4B speed and vision;
  - screen-per-prompt answers;
  - delegation chosen by the brain ("ask Pip…");
  - memory across restart.

  LM Studio held about 10 of the 16 GB and was in active use. These checks are in the acceptance
  guide.
- **Not run: voice, the avatar, and native GUI interaction.**
- **E4B projector.** `mmproj-F16.gguf` was already beside the E4B model. A download I started
  without checking the exact filename **replaced it**. The file is byte-identical: the original
  download's `.cache/huggingface` metadata hash, the new file's hash and Hugging Face's hash all
  equal `ddf46c21…`. No data was lost, but I record the mistake here.
- **The keyword router ignores negation.** "Do not … edit files" was classified as a write. This
  is left for the decision layer, and documented in `V1.md`.

## Verification

Final full gate on the finished code, on the owner's Windows machine:

- `ruff check`: clean. `mypy --strict`: clean (298 files). `export-contracts.py --check`: clean.
  `compileall`: OK.
- `pytest`: **971 passed / 25 skipped / 4 strict expected failures**. That is 962 plus 9 new tests:
  6 in `tests/runtime/test_task_reports.py` and 3 in `tests/providers/test_process_tree.py`.
- `dotnet test`: 369/369. desktop_shell, desktop_app and desktop_widget build with 0 warnings and
  0 errors. PWA: 8/8. `verify-shell-launchers.ps1`: passed.
- **Stability.** The new timing-sensitive tests passed 25 runs in a row. Over about 12 full-suite
  runs:
  - **one run had a single failure whose name was not captured** (`-rf` was off). It did not
    recur in the following 11 runs, and it is unresolved;
  - an intermittent "unclosed transport" warning (about 1 run in 4) came from agent stdin pipes
    that were never closed. `OwnedProcess.close()` now closes stdin, and the next 2 runs were
    clean.
