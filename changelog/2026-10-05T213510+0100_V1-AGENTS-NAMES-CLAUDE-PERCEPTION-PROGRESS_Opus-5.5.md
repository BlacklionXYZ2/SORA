# Agent names, a Claude Code adapter, screen-on-prompt default and the motion interface design

Model name: **Opus 5.5**. Checkpoint **2026-10-05 21:35:10 +01:00**, Europe/London. Status:
**implemented, component-tested only**. This moves [V1.md](../V1.md) acceptance steps 4, 5 and 6
forward but closes none of them. Nothing was run natively, against a live model or with Claude
itself. Work was done in a Linux cloud container at the owner's request.

## Changes

- **Agent names and spoken aliases (step 6).** New `src/sora/routing/agent_names.py` is the one
  table of what SORA calls her colleagues: Cody (Codex), Hermes, Aggie (Antigravity) and Claude.
  It holds speech-to-text variants ("codey", "kodi", "aggy", "anti gravity", "clawed"…) and
  supports owner nicknames for custom endpoints, rejecting clashes. Ordinary words such as
  "cloud" and "code" are deliberately not aliases. It is used by:
  - steering and voice cancel (`RoutingEngine.disambiguate_steering`). These now also match
    auto-routed tasks, whose records carry the adapter ID (`codex-app-server`) rather than the
    routing key. Before this, "tell Cody to stop" could not find an auto-routed Codex task;
  - the explicit-request check in companion delegation ("ask Aggie…", "hand it to Claude"),
    which previously matched only `codex|hermes|antigravity`. Naming two agents now asks which
    one is meant;
  - result attribution (`present_result`): Antigravity results are credited to "Aggie".
    `tests/runtime/test_multi_provider_routing.py` was updated to match.
- **Claude Code adapter (step 6).** New `src/sora/providers/claude_code.py` runs headless
  `claude -p --output-format json` with the prompt on standard input, so no Windows command-line
  length or quoting limit applies. It captures and resumes native sessions, maps `--model`,
  cancels and times out, and reports CLI errors (`is_error`, error subtypes) instead of parsing
  them. It adds **no permission flags**: print mode denies tools that would need approval unless
  the owner passes `--claude-arg`. `src/sora/__main__.py` adds `--claude-command`, `--claude-arg`,
  `--claude-cwd` and `--claude-model`; `--provider auto` registers Claude when `claude` is on
  `PATH`. The router classifies `claude` as hosted, like Codex, so the existing local-only rule
  applies to it.
- **Screen with every prompt (step 4).** `PerceptionSettings.mode` now defaults to
  `image-on-prompt`. Voice turns use the same dialogue path, so this covers text and voice.
  Settings migrated from v2/v3 (before perception existed) keep `native-only`, so an upgrade never
  switches automatic images on. Existing saved settings are unchanged. Updated
  `config/sora-settings.example.json` and the exported `app-settings` schema. The shared helper in
  `tests/voice/test_companion_parity.py` pins `native-only`, because those voice tests have no
  capture helper.
- **Motion interface (step 5, design only).** New
  `docs/plans/MOTION_INTERFACE_DESIGN_2026-10-05.md` proposes one `MotionSignal` stream (intent,
  conversation state, emotion, attention, audio envelope, context) for both the deterministic
  layer and the owner's future learned model. Nothing is implemented.
- **Docs.** The `V1.md` status rows for agents, screen and movement were updated in place, and the
  local try-out runbook now documents Claude.

## Verification (component and fixture only)

- `uv run --locked pytest -q`: **929 passed / 29 skipped / 6 strict expected failures / 8
  failed**. The same 8 fail on the unchanged source in this Linux container (Windows paths and
  `python.exe`); before the change it was 896 passed with those 8 failing. New tests:
  `tests/routing/test_agent_names.py` (19) and `tests/providers/test_claude_code.py` (14, using
  a fake `claude` script).
- `ruff check src tests scripts`: clean. `mypy --strict --platform win32 src tests`: clean on 289
  files. Without `--platform win32`, Linux reports Windows-only module attributes, unrelated to
  this change.
- `python scripts/export-contracts.py --check`: clean after re-exporting `app-settings`.
- .NET 10.0.401 on Linux, with `EnableWindowsTargeting`: `dotnet test` 353 passed / 16 failed,
  the same as before the change (the 16 start `powershell.exe`). Shell host, full app and widget
  build with 0 warnings and 0 errors. No C# file changed.

## Not done, and why

- **Privacy routing (V1 privacy row)** was not changed. The edit that would let local-only and
  private context reach hosted agents was refused by this session's automated safety check as
  security-weakening. It needs the owner to approve it, or to make the change themselves. The
  two strict expected failures in `tests/verification/` stay as they are.
- **Custom endpoints, catalogue names and a Claude row in the delegation catalogue** were not
  done. The delegation-catalogue edit that adds Claude and the custom-endpoint slots, and shows
  SORA's names in the Agents panel, was refused by the same check. Custom endpoints depend on it
  (and on settings v10). "Ask Claude…" works through the explicit-request path, but the local
  model's `delegate` vocabulary still lists only codex, hermes and antigravity.
- **Gemma 4 E4B** needs the owner's model and projector files, chosen in Settings. Nothing here
  could do that.
- Not run: Claude Code itself, the real local model, native GUI, microphone, or the owner's
  machine. A Windows check is still needed that `claude` launches from `PATH` (a `.cmd` shim
  from npm or the native `claude.exe`).
