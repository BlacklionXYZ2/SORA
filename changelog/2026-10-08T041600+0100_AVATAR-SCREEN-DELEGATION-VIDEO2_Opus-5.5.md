# Avatar wired into the GUI test video; SORA sees the owner's window, not her own Chat; custom agents by nickname

Model name: **Opus 5.5**. Checkpoint **2026-10-08 04:16:00 +01:00**, Europe/London. Status:
**implemented, component-tested, checked natively in isolated profiles, and recorded.** It is not
a stage completion. The owner asked: "can you wire up the 3D model too in the next testing video?
The actual spatial presence is one of SORA's key differentiating features, also your tests stated
that SORA couldn't see the desktop?" This moves V1 steps for presence (avatar movement on request),
seeing the screen and agents (custom-agent delegation) forward in the new GUI.

## Why "SORA couldn't see the desktop" in video 1

There were two causes:

1. **My test setup.** For video 1 I started Core directly, not through `Start-SORA.ps1`. Only the
   managed launch wires the capture, observation and press/type helpers. Video 2 uses
   `Start-SORA.ps1 -StateRoot … -ShellPanel chat -HiddenCore`.
2. **A real bug.** Image-on-prompt attaches the window of the most recent non-SORA foreground app.
   The new shell's process, `SoraShell.exe`, was missing from `COMPANION_PROCESSES`, so typing in
   Chat made SORA's own Chat the "recent app". She then described her own Chat window.

## Changes

1. **`src/sora/desktop/foreground.py`:** added `sorashell.exe` to `COMPANION_PROCESSES`. New test
   `test_typing_in_the_native_app_keeps_the_owners_previous_application`.
2. **Agent roster in every companion turn** (`DelegationCatalogue.roster()`, used in
   `runtime/read_turn.py`).
   - Each enabled agent gets one line, "name = provider: purpose", on the observations header line.
   - Before this, window and file records could trim the agent preview out of the budget. E4B
     then replied "I don't have access to Pip".
   - The format stays "one header line, then JSON". A first version put the roster on its own
     line, and the full suite caught that it broke the two test callers that parse this format.
3. **Delegation reference handling** (`DelegationCatalogue.select`).
   - An agent's name or provider ID in the `model` field ("model": "Pip") now selects that agent
     with its default model.
   - For chat-only custom agents, an invented model or project reference is ignored. They have
     only their configured model and no project folder.
   - For every other agent, unknown references still refuse, as before.
   - New test `test_agent_roster_and_project_references_survive_small_model_mistakes`.
4. **Move prompt** (`contracts/companion_call.py`, prompt text only, no schema change).
   - "Always set place for screen; it is centre only when the owner says centre or middle."
   - Added a worked example for running to the left and sitting.
   - Before this, "run to the left side of the screen" went to the centre.
5. **Chat and Activity learn agent names until Core answers** (`shared/tasks.js`
   `agentNamesKnown()`, `chat.js` and `activity.js` `learnNames()`). A chip read "Asked Agent 1"
   when the window opened before Core was ready.
6. **Unity player rebuilt.** `clients/unity/Builds/Windows/SORA.exe` dated from 2026-09-09. I ran
   `SoraBuild.Prepare` and then `SoraBuild.Windows`, with logs in my scratchpad so the P09 evidence
   logs were not overwritten. This is a build output, not a source change.
7. **HOW_TO_USE.md:**
   - setup step 4 now says to rebuild the avatar, since `Start-SORA.ps1` does not;
   - the screen image is your previous window;
   - custom agents can be asked by nickname;
   - the "Last updated" line is new.

## Video 2

Path: `.local/videos/SORA_GUI_test_2_avatar_2026-10-08.mp4`, about 3 minutes, 1920×1080, with
captions. It was recorded in the isolated profile `.local/<demo profile>`, port 18993, llama on
18877, through `Start-SORA.ps1`.

Steps, in order:

1. Settings: change the model to E4B through the native file dialog.
2. Wave.
3. "Run over to the left side of the screen and sit down." She ran left (x ≈ 576) and sat.
4. "Come over here please." She walked to the pointer.
5. "What can you see on my screen right now?" She described the test backdrop text, "GUI test run
   · isolated test profile".
6. A memory question.
7. Delegation to the custom agent "Pip" (a local fake agent), then Activity.
8. Voice.

Privacy:

- The demo profile turned `desktop_context` and `window_context` off.
- `list_windows` still lists open window titles, which it does by design. I blurred that list in
  the render, along with the file dialog's navigation pane, and checked the blur frame by frame.
- Teardown killed only the demo host and its Core tree. The owner's SORA and Hermes's llama
  (port 18434) were not touched.

## Verification

- **Fixture/component:** `.\scripts\verify.ps1` ran ruff, mypy (310 files), pytest (1021 passed,
  25 skipped, 4 xfailed) and the PWA/panel tests (31 passed), exit 0.
  `dotnet test clients/csharp_tests/csharp_tests.csproj` gave 404 passed.
- **Native:** the managed launch in isolated profiles, with avatar connection, move, sit and walk
  to the pointer confirmed through `/api/v1/projections/embodiment` and on screen.
- **Live model:** E4B (`gemma-4-E4B-it-Q4_K_M`) chose move, pose, delegate and the screen
  description in the video. These are single runs, not a reliability measure.
- **Not run:** hardware or opt-in native test suites, the owner's real profile, and a real
  third-party agent (Pip was a local fake OpenAI-compatible server).

## Findings, not fixed

- The avatar spawns at the top-left and crosses the sky diagonally to the floor on first connect.
- The wave is barely visible, and she is small on a 4K monitor.
- The "Used 1 memory" chip did not appear on the memory answer in video 2. I did not investigate.
- `list_windows` exposes the owner's window titles to the model and the transcript. This is by
  design under `desktop_observe`, but worth a deliberate decision.

HOW_TO_USE.md: updated.
