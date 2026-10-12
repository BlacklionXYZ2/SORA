# Quit closes every part of SORA

Model name: **Opus 5.5**. Checkpoint **2026-10-09 21:00:00 +01:00**, Europe/London. Status:
**implemented, component-tested; not yet tried on the owner's running SORA.** The owner asked
for closing the app to end Laya, the llama server, `sora.exe`, `SORA.exe` (the avatar) and
`SoraShell.exe`.

## Why the old Quit wasn't enough

- It asked Core to shut down gracefully and, if that couldn't be confirmed, kept the host open
  and deliberately force-stopped nothing.
- The process tree can't be used to find the helpers: on the owner's machine the tree is
  SoraShell → PowerShell → uv → sora.exe → python → Store python3.12 → avatar and Laya, while
  `llama-server`'s parent (the llama.cpp worker) has a parent that no longer exists. Hermes also
  runs its own `llama-server`, so stopping processes by name is unsafe.

## Changes

- New `src/sora/helper_processes.py`:
  - when Core serves for the desktop host, it sets `SORA_STATE_ROOT`, which child processes
    inherit;
  - each helper's process ID goes in `<state root>/private/helpers/<name>.pid`: `core`,
    `llama-server` (recorded by the llama.cpp worker), `laya`, `avatar` and `voice`;
  - recording is off otherwise and never fails a start.
- Calls in `__main__.py`, `providers/llama_server.py`, `decision/laya.py`,
  `embodiment/local_player.py` and `voice/windows_bridge.py`.
- New `clients/desktop_shell/HelperCleanup.cs`: stops each recorded helper still running, but
  only when the program name matches what's expected and it started after this host launched
  Core, so a reused process ID is never hit.
- `ShellCoreCoordinator.CloseEverything()`: the recorded helpers, then the launcher's whole
  process tree; the descriptor is marked stopped. An attached external Core is never touched.
- `ShellHost.QuitAsync`: graceful Core shutdown first, then `CloseEverything()`, then the app
  exits even if graceful shutdown couldn't be confirmed. The menu item is now "Quit SORA", and
  the confirmation text says what closes.
- Owner decision: this deliberately replaces the earlier "never force-stop services" Quit design
  (recorded here).
- HOW_TO_USE.md: the Quit line lists what closes; "Last updated" line updated.
- Tests: `tests/test_helper_processes.py` and `clients/csharp_tests/HelperCleanupTests.cs`
  (linked in the test project).

## Verification

- Component:
  - C# tests 407 passed, including the two new ones;
  - desktop shell build has 0 warnings and 0 errors (built to `.local/quit-qa-2026-10-09/build`,
    so the owner's running SoraShell was not touched);
  - Python: ruff and strict mypy clean; pytest 1096 passed, 25 skipped, 4 xfailed. The first
    run had 15 failures: test doubles for processes have no `pid`, so the record calls now
    tolerate that.
- **Not run:** a real Quit of a full SORA. The owner's running SORA started before this change,
  so it still has the old Quit and no helper records. The new behaviour applies from the next
  launch after quitting.
