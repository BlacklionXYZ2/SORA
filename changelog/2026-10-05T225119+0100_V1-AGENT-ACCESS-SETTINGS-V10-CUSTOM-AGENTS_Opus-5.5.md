# Hosted agents get project write access; settings v10 adds Claude, custom agents and usage descriptions

Model name: **Opus 5.5**. Checkpoint **2026-10-05 22:51:19 +01:00**, Europe/London. Status:
**implemented, component-tested only**. Moves [V1.md](../V1.md) steps 6, 7 and 8 forward and
closes none of them. This supersedes the "Not done" section of
[the previous entry](2026-10-05T222115+0100_P06-PRIVATE-CONTEXT-HOSTED-AGENTS_Opus-5.5.md): after
the owner switched the session out of Auto mode, the work it describes was done.

## Owner decisions implemented

Hosted agents are trusted with private context and with file writes. Delegation covers every
available agent, each with a default usage description the owner can overwrite (including a
general one for custom agents), so SORA can choose by preference and circumstance.

## Changes

- **Write access (commit `632cafd`).**
  - A new `ProjectRootProvider` surface (`src/sora/providers/base.py`) lets Claude and Antigravity
    work directly in an owner-selected project folder, in read-only or direct mode.
  - Core still holds the per-root writer lease and records the before/after diff, as it does for
    Codex direct mode. Isolated worktrees stay Codex-only.
  - `__main__` now passes `--permission-mode bypassPermissions` to Claude Code and
    `--dangerously-skip-permissions` to Antigravity by default. The opt-outs are
    `--claude-ask-permissions` and `--antigravity-ask-permissions`; explicit `--claude-arg` /
    `--antigravity-arg` still replace the defaults. `scripts/start-full-sora.ps1` maps its
    existing `-NoAntigravitySkipPermissions` to the new opt-out.
- **Settings v10 and the delegation catalogue (commit `c46002a`).**
  - `AgentPreferences` adds `claude` and `custom_1`…`custom_4` (enabled, nickname, spoken aliases,
    port, default model, usage description). There are default descriptions for every agent in
    `DEFAULT_PURPOSES`.
  - v7–v9 files migrate with the usual backup and keep the owner's own text. 117 settings fields,
    up from 84. Custom-agent fields take effect at the next start; descriptions are live.
  - The catalogue shows SORA's names (Cody, Hermes, Aggie, Claude, nicknames), spoken aliases
    and descriptions. The delegation catalogue and the companion `delegate` vocabulary include
    `claude` and `custom-1`…`custom-4`, and the prompt tells the model to choose by description.
  - Router and catalogue take nicknames from startup settings.
  - C# clients accept v10 through one `SettingsDraftState.CanonicalVersion` constant, and the
    C# tests were updated.
- **Custom agents (commit `b037bf1`).** New `src/sora/providers/custom_endpoint.py` calls
  `http://127.0.0.1:<port>/v1/chat/completions` (no proxies). It credits results to the nickname
  and reports unreachable, HTTP-error, empty and cancelled runs honestly. Enabled slots are
  registered at startup. The answer normaliser is shared with the Claude adapter.
- **Docs:** the `V1.md` agents, privacy and settings rows and the roadmap §4.0 version line were
  updated in place, and the local try-out runbook was updated.

## Verification (component and fixture only)

- `pytest`: **946 passed / 29 skipped / 4 strict expected failures / 8 failed**. The same 8 fail
  on unchanged source in this Linux container (Windows paths and `python.exe`). New tests:
  `tests/runtime/test_hosted_agent_projects.py` (a fake Claude edits a real git project in direct
  mode, twice, releasing the writer lease between runs), `tests/runtime/test_agent_settings_v10.py`
  and `tests/providers/test_custom_endpoint.py` (mock HTTP transport, plus an end-to-end runtime
  delegation to "Pip").
- `ruff`: clean. `mypy --strict --platform win32`: clean on 293 files. Schema export check:
  clean (`app-settings`, `companion-call` and `settings-edit` re-exported).
- .NET 10 on Linux: Shell host, full app and widget build with 0 warnings and 0 errors.
  `dotnet test`: 353 passed / 16 failed, the same 16 as before any change in this session (they
  start `powershell.exe` or need Windows launch prerequisites).

## Limits and next

- Not run: real Claude Code, Antigravity or a real custom harness; the local model choosing
  agents from descriptions; native Settings rendering of the new fields; the owner's machine.
- Unenforced by design: with permission prompts off, an agent working in a project folder can
  write anywhere its CLI allows. Core records the diff only for the selected folder.
- Custom agents speak the OpenAI-compatible chat API only. Agent Client Protocol harnesses still
  need an adapter.
