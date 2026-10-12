# Glass Activity window, safer Quit and file picker, and a test video of the GUI

Model name: **Opus 5.5**. Checkpoint **2026-10-07 23:00:00 +01:00**, Europe/London. Status:
**built, component-tested, checked natively in isolated profiles, and recorded.** The owner
asked: "Continue, and would you mind making a testing video showing everything working?" This
moves [WebView2 rewrite](../docs/plans/GUI_WEBVIEW_REWRITE_2026-10-06.md) stage W5 (Activity)
forward, along with V1 step 5 (agents) in the new GUI.

## What changed

1. **Web Activity window** (`clients/panels/activity/`, opened by the tray, the command menu and
   Chat).
   - **List:** agent tasks, with SORA's name for the agent and Core's status in plain words.
   - **Detail**, in reading order:
     - the owner's request;
     - SORA's brief, labelled "not your words";
     - the agent's report, labelled as its report: summary, failure, files changed, commands
       run, warnings and progress notes;
     - Core's coverage note.
   - **Cancel task** (with an in-window confirm) and **Send instruction**, only for statuses Core
     accepts them in.
   - Refreshes every 4 s.
   - A summary that the conclusion repeats is shown once, and codes such as `changelog_missing`
     read as words.
2. **Chat task chips open Activity on that exact task.**
   - `panel.open` takes an optional `select` (an exact Core ID, validated in JS and C#).
   - The host sends it to the page as `host.select` once the page has reported ready.
3. **Agent names come from Core's agent catalogue,** so custom agents show their nickname (for
   example "Pip"). Built-in IDs such as `codex-app-server` still read as Cody.
4. **Quit asks before discarding unsaved Settings edits.**
   - The page reports `panel.dirty`.
   - Quit from the tray asks for confirmation.
   - A pipe/command `quit` is refused while edits are unsaved.
5. **The file picker opens in the current model's folder.** `file.pick` takes an optional
   `start`, used only if it is an existing, fully qualified local folder; network paths are
   ignored. It no longer opens in the owner's Documents.
6. Shared task words moved to `clients/panels/shared/tasks.js`, used by Chat and Activity.

## The test video

`.local/videos/SORA_GUI_test_2026-10-07.mp4` (1920×1080, 2 min 38 s, captioned; local only, not
committed).

**How it was made:**
- An isolated profile (`.local/gui-demo-take3-20261007`) with its own Core and E2B, and a fake
  OpenAI-compatible agent "Pip" (a local script that waits 8 s and replies), so no hosted agent
  was used.
- A full-screen stand-in backdrop, so none of the owner's windows appear.
- The real SoraShell windows, driven through the WebView2 debugging port by
  `scratchpad/video/demo.mjs`, and recorded with ffmpeg (`ddagrab`).
- The native file dialog was answered with typed keys.
- Captions were burned in afterwards. The dialog's left navigation pane (OneDrive account name
  and a network share) is blurred for the 12 s it is visible.

**What the video shows, all real and unedited apart from the captions and that blur:**
1. Glass Chat over the backdrop. A formatted list reply, then evidence chips that open.
2. "Remember my sister's birthday…", then a question about it, answered with a **Used 1 memory**
   chip.
3. "Ask Pip to…": SORA queues a real task, and the chip goes from **Asked Pip · Thinking** to
   **Done**.
4. Clicking the chip opens Activity on that task, showing the request, brief and report.
5. Voice: one click starts it (amber, then green). Holding turns it red. Leaving the window
   discards the recording.
6. Settings Models card and tiles. A Vision setting saved and reverted.
7. **Change model:** picking E4B in the native dialog finds its projector automatically; Save and
   reload, then the card shows **Loaded** with E4B.

**Takes:**
- Take 1 placed the windows wrongly: they restore their saved size after showing.
- Take 2 stopped when Settings opened on Advanced: the pointer was resting over the window.
- Take 3 is the final one: the windows are placed twice, the pointer is parked on the other
  monitor, and Models is clicked explicitly.

## Verification

| Kind | What | Result |
|---|---|---|
| Component (JS) | Panel tests, including Activity sections, selection validation, catalogue names, repeated-summary and code wording | 31 passed |
| Component (C#) | `csharp_tests`, including `select`, `panel.dirty` and start-folder cases | 404 passed |
| Native, isolated | Real delegation to Pip through SORA's companion call (`custom-1`): task created, completed and shown | Passed (QA, then the video) |
| Native, isolated | `--show quit` with an unsaved Settings edit, then after Discard | Refused and SORA stayed open; after Discard, SORA quit |
| Native, recorded | The full video run | All 21 steps passed in take 3 |
| Fixture (full) | `scripts/verify.ps1` | 1019 passed, 25 skipped, 4 xfailed; mypy clean on 310 files; PWA 8/8; panels 31/31 |

## Not verified, or found

- The tray-menu Quit confirmation was not clicked natively; only the pipe-quit refusal was tested.
- A refused pipe quit leaves the forwarding process showing "Existing profile host did not accept
  this command", which doesn't say why (behaviour that predates this change).
- No real hosted agent (Cody, Hermes, Aggie, Claude) was run through Activity; the video uses the
  local stand-in.
- The video has no audio. Voice is shown starting and listening, but no spoken turn: the test
  discards the recording.
- The QA and demo profiles under `.local/` were left in place.

HOW_TO_USE.md: updated (Activity, the window list, task chips opening the exact task, Change
model folder, Quit asking about unsaved Settings).
