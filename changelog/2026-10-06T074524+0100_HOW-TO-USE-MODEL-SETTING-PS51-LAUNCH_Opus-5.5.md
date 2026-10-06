# How-to-use guide, findable model setting, and two launch fixes found by actually launching

Model name: **Opus 5.5**. Checkpoint **2026-10-06 07:45:24 +01:00**, Europe/London. Status:
**implemented. Component-tested, plus native checks of the native app in isolated QA
profiles.** This moves [V1.md](../V1.md) steps 1 and 8 forward.

## Why

The owner asked: "There isn't a setting to change the model?" Opening the native app's Settings
in an isolated profile showed that the setting existed but could not reasonably be found.
Launching it also exposed two launch bugs that neither the tests nor the launcher verifier had
caught.

## Changes

- **The model setting is findable.**
  - In Core's settings metadata (`src/sora/runtime/app_settings.py`), the brain's model and
    projector files get their own group, **"Brain (local model)"**. It is now the first group
    in Settings → Models.
  - The fields are relabelled **"Brain model file (GGUF)"** and "Vision projector file (GGUF,
    found automatically beside the model)".
  - The external-server fields come next, under "External server (only when Model source is
    external)", as "External server model ID" and "External server URL".
  - Before this, the first field was an empty external "Model" box, and the real model picker
    sat below the fold under "Model & performance".
- **Ampersands in Settings headings.** Headings and labels in the shared settings editor
  (`clients/desktop_app/ModelSettingsEditor.cs`) set `UseMnemonic = false`, so "Model &
  performance" no longer renders as "Model  performance".
- **The default launch failed on Windows PowerShell 5.1** (the owner's only PowerShell).
  - `Start-SORA.ps1`'s native-app branch used `ProcessStartInfo.ArgumentList`, which exists only
    on PowerShell 7. On 5.1 it is null, so the launch failed with "You cannot call a method on
    a null-valued expression". This had been broken since that branch was written.
  - My change from the previous entry made it the default, so a plain `.\Start-SORA.ps1` would
    have failed. That change was never committed, so it never reached the owner.
  - The arguments are now joined with a Windows command-line quoting function
    (`ConvertTo-NativeArgument`). It was round-trip tested on PowerShell 5.1 with spaces,
    quotes, trailing backslashes and empty values.
- **Starting failed whenever an old SORA window was open.**
  - `scripts/start-manual-test.ps1` rebuilt the frozen full app and widget, and stopped the
    whole start if either build failed. The owner's open full app locked its `.exe`, so after
    any change to their shared code, SORA's Core would not start.
  - Helper builds still stop a start if they fail. The frozen apps now only warn: "Could not
    rebuild … (is it open?)". This was verified live with the owner's full app open.
- **New `HOW_TO_USE.md`.** A plain-language manual for SORA as it is today: start and stop, the
  Chat shortcut, first-time setup (brain model, vision mode, voice, freeing the GPU), talking,
  voice, moving and pointing, memory, agents and custom agents, known limits, and a
  troubleshooting table. Every claim was checked against code or runbooks.
- **Keeping it current.**
  - `AGENTS.md` has a new hard rule: any change to how SORA is started, set up or used updates
    `HOW_TO_USE.md` in the same change.
  - `changelog/README.md`: entries end with "HOW_TO_USE.md: updated / no change to usage".
  - The README links the guide first. `V1.md` and `docs/runbooks/SORA_SETTINGS.md` use the new
    names.
- **Regression tests** (`tests/test_launcher_powershell51.py`):
  - the launcher must not use `.ArgumentList`. The committed launcher fails this check;
  - quoting must round-trip through real Windows PowerShell 5.1.

## Verification

- Native app in isolated QA profiles (separate state folders and ports, no avatar, offline
  dialogue model):
  - launched through the fixed launcher on PowerShell 5.1;
  - Settings → Models was screenshotted before and after. After: "Models · Brain (local model)"
    is the first group, with the browse button;
  - Core started with the owner's full app open, and the new warning was observed.
  - All QA processes were stopped afterwards. The owner's SORA, model servers and open app
    windows were untouched throughout. One stray QA failure was caused by my own force-stop
    leaving a stale profile; it is not a product bug.
- **Leaked pipe traced and fixed.** The intermittent "unclosed transport" warning came from Hermes
  runs: Python's allocation trace pointed to `OwnedProcess.start`. After a run was stopped, its
  stdout pipe was never read to the end. `OwnedProcess.close()` now closes the subprocess
  transport, which closes all of its pipes. Three provider-folder runs with warnings enabled
  were then clean.
- `tests/runtime/test_companion_reads.py::test_normal_launcher_wires_native_observation` matched
  the launcher's old list layout, `$typeProject,` with a trailing comma. It now checks the
  intent: each native helper appears in the build list whose failure stops the start.
- **Final full gate on the owner's Windows machine:**
  - `ruff` clean; `mypy --strict` clean (299 files); schema check and `compileall` OK;
  - `pytest` **973 passed / 25 skipped / 4 strict expected failures, twice in a row, with no
    warnings or failures**;
  - `dotnet test` 369/369; zero-warning builds of desktop_shell, desktop_widget and desktop_app.
    desktop_app was built to a separate folder because the owner's copy was open;
  - PWA 8/8; launcher verifier passed.

## Limits and next

- The Settings window's other categories were not reviewed for the same findability problem.
- The `-Client Shell` path had never worked on PowerShell 5.1, so other native-app launch
  behaviour on the owner's machine is also untested until the owner's V1 run.

HOW_TO_USE.md: updated (new).
