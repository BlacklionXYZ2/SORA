# Runtime reasoning-backend selection, file-action routing and local defaults — Deepseek V4.1 Flash

Model name: Deepseek V4.1 Flash

Status: **implemented / in review at 2026-09-27 17:02:43 +01:00 (Europe/London)**. This is an
uncommitted working-tree change set requested by the owner while getting the current checkout into a
usable personal state. It is **not** a phase or release completion, and per the owner's instruction
**nothing was committed** (`git log` still ends at `89f005f`).

## Owner direction that shaped this work

1. Gemma 4 E2B is the intended default dialogue model because it has to react in real time.
2. The reasoning provider should not be pinned at startup; SORA should choose per task at runtime.
3. The API-backed specialists (Hermes, Codex, Antigravity) exist so delegated work can actually
   affect the system — file creation and project work.
4. Do not add features; get the current state working. Do not commit.

## Files changed (5)

### `src/sora/__main__.py`

- `--provider` accepts `auto` and now defaults to it (`SORA_PROVIDER`, default `auto`). In `auto` mode
  every backend that is actually usable on this machine is registered, so the existing rule-based
  routing engine chooses per task at runtime instead of the process being pinned to one backend.
- Provider construction moved into `build_provider_registry()` returning a `ProviderPlan`
  (registry, skipped reasons, effective Codex cwd); `ProviderSetupError` carries the previous
  fail-closed messages.
- Registration rules: a backend is registered when its CLI resolves on `PATH` and its working
  directory exists. `hermes`/`codex` fall back to the delegation workspace; `deterministic` is always
  registered as the offline fallback. An explicit `--provider NAME` keeps the previous behaviour
  exactly — one backend plus the deterministic fallback, and a missing `--hermes-cwd`/`--codex-cwd`
  still exits `2` before any database is created (covered by `tests/test_scaffold.py`).
- New `--workspace-root` (default `<root>/workspace`): the delegated working directory used when a
  backend has no explicit directory of its own.
- New `--antigravity-arg` (repeatable), wired into the existing `AntigravityProvider(args=...)`
  parameter so `agy` flags such as `--dangerously-skip-permissions` can be configured per machine.
- Managed Codex coding writes are no longer tied to `--provider codex`; they enable whenever a Codex
  working directory and `--codex-write-base` are both present, which is what lets `auto` route writes
  into an owned worktree.
- `--serve` prints the registered backends and any skipped-backend reasons; the interactive banner
  reports auto routing instead of a single provider.

### `src/sora/routing/router.py`

- Added `_FILE_ACTION_PATTERNS` and used it in `classify_intent()` alongside `_CODING_WRITE_PATTERNS`.
  Before this, natural wording such as *"Create a file named X"* matched no rule and fell through to
  the general-reasoning rule, so it went to the reasoning specialist instead of the coding specialist
  and was never submitted as a coding write. Verified live before and after (see below).

### `tests/routing/test_routing.py`

- `test_coding_write_classifier_recognizes_file_creation_wording` — four phrasings classify as
  `CODING_WRITE` and route to `codex`.
- `test_file_action_wording_does_not_capture_plain_research` — plain research wording still
  classifies as `RESEARCH`.

### `scripts/start-manual-test.ps1`

- Starts Core with `--provider auto`, `--workspace-root`, `--task-timeout` and the managed-write
  arguments (`--codex-cwd`, `--codex-write-base HEAD`, `--codex-workspace-root`).
- New parameters: `-WorkspaceRoot`, `-WriteRepo`, `-TaskTimeout` (default 300; the previous default
  was 30s, which is shorter than a real specialist turn).
- Dialogue model defaults to `gemma-4-e2b-uncensored-hauhaucs-aggressive-q4_k_p`. When LM Studio is
  answering, Core starts on that model; when it is not, the script warns clearly and starts on the
  offline fixture instead of failing. An explicitly passed `-DialogueModel` that cannot be reached
  still throws.
- The delegation workspace is initialised as a Git repository (one empty commit) when it is not
  already one, so managed coding writes have an owned base instead of failing for lack of a repo.
  Save settings still take precedence over these startup flags on restart.

### `docs/runbooks/SORA_LOCAL_TRYOUT.md`

- Corrected the statements that said these scripts run delegated tasks on the deterministic fixture
  and launch no external agent, and the instruction to use **Delegate** only for fixture workflow.
- Documented the delegation workspace, `-WorkspaceRoot`, `-WriteRepo`, and that coding writes run in
  an owned worktree below the test state rather than in the source checkout.

## Runtime actions taken on this machine (not file changes)

- Stopped the previously running Core (`sora.exe` PID 48452), Unity avatar (`SORA.exe` PID 25916) and
  full desktop app (`SoraDesktop.exe` PID 54692); started Core plus avatar three times on port 18769
  while iterating. **The desktop app is currently closed** and was not relaunched.
- Created `.local/manual-test/workspace` and initialised it as a Git repository (single empty commit,
  "SORA delegation workspace").
- Submitted four tasks to the live Core (see verification), probed LM Studio read-only, and ran three
  `codex exec` probe commands.

## Verification

| Check | Result |
|---|---|
| `ruff check` on changed source and test files | clean |
| `mypy` (strict) on `__main__.py` and `router.py` | clean |
| `pytest -q -x --ignore=tests/desktop` | **317 passed, 5 opt-in skipped** |
| `pytest tests/routing tests/test_scaffold.py` | 20 passed (includes the two new tests and the unchanged fail-closed CLI tests) |
| Registry probe (`build_provider_registry` across four argument sets) | `auto` → antigravity, codex, deterministic, hermes; `--provider deterministic` → deterministic only; `--provider hermes` without a cwd → the original error message |
| Live `/api/v1/status` after restart | providers: `antigravity, codex, codex-app-server, deterministic, deterministic-mock, hermes, hermes-acp`, all `available: true` |
| Live settings projection | revision 2 active, `restart_required: false`, dialogue model `gemma-4-e2b-uncensored-hauhaucs-aggressive-q4_k_p` |
| Live delegation to Hermes (explicit) | **completed**. Real task: ran `ls`, a recursive search, `git log/status/ls-files`, `git show --stat` (4 tool calls) and returned a structured summary, `files_read`/`actions_taken`/`uncertainties`, plus usage reporting `deepseek-flash` via `deepseek` on `acp`. |
| Live coding-write classification | Before the router change "Create a file named …" routed to `antigravity`; after it routes to `codex-app-server`. |

## Live findings that block the owner's file-creation goal (not fixed here)

1. **Codex is out of usage.** `codex exec --model gpt-5.6-luna` returns
   *"You've hit your usage limit … try again at 8:47 PM"*. Coding writes are therefore submitted
   correctly but cannot execute until the account limit resets. The owner's global Codex config also
   selects `gpt-6-sol`, which the API rejects for a ChatGPT account
   (*"not supported when using Codex with a ChatGPT account"*).
2. **Antigravity auto-denies tools in headless print mode.** `agy` reports
   `denied_actions: [{"action":"command","display_name":"RunCommand"}]` and writes to stderr that a
   tool "required the \"command\" permission that headless mode cannot prompt for, so it was
   auto-denied; add an allow-rule under permissions.allow in settings.json … or re-run with
   --dangerously-skip-permissions." The empty `response` is what surfaced as *"The provider returned
   malformed output."* `--antigravity-arg` now exists so this can be configured, but nothing was
   changed in the owner's `agy` settings.
3. Because the router prefers Antigravity for research and general reasoning, those two categories
   currently fail for tool-using prompts until (2) is configured.

## Boundaries and current state

- Nothing was committed or staged; the trailing `git status` count is unchanged apart from these
  files.
- No live Codex or Antigravity task has ever completed on this machine, and no claim is made that
  either works. Hermes delegation is verified end-to-end.
- A single Core (`--provider auto`) and the Unity avatar are running on `127.0.0.1:18769`; the desktop
  app is closed.
- The workspace Git repository is a fresh empty base and contains no project files; `-WriteRepo` is
  the supported way to point the managed write path at a real repository.
- Documentation elsewhere (README, implementation plan) was not updated, so it still describes the
  previous `--provider` behaviour.
