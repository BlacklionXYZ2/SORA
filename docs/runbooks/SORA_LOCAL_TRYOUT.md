# Try SORA locally from this checkout

This is a developer/manual test setup, not an installer or release acceptance. It keeps state in
`.local/manual-test`, separate from an installed SORA release, binds Core only to `127.0.0.1`, and
registers every reasoning specialist installed on this machine so SORA routes each delegated task at
runtime (Hermes, Codex, Antigravity and Claude Code when their CLIs are on `PATH`); the offline
deterministic fixture stays registered as the fallback. Claude runs headless (`claude -p`) on your
Claude subscription and is only used when you name it ("ask Claude…"). SORA adds no permission
flags, so by default it can read and answer but not edit; pass `--claude-arg` (for example
`--claude-arg=--permission-mode --claude-arg=acceptEdits`) to Core if you want it to edit, and
`--claude-model` to pick a model.

## One-command start

**Current Settings update:** after startup, open **Settings** in the full app to choose the GGUF,
projector, cache types, context, GPU offload, flash attention and speculative mode. Save stages
model changes; **Reload model** applies them without restarting Core. The unified JSON store is
created by automatic legacy import; after that GUI settings take precedence over legacy launch
arguments. See [the Settings guide](SORA_SETTINGS.md). No manual file editing is needed.

**2026-09-28 update:** This computer now has `.local/llama-server.json`, so the
normal launcher loads Gemma 4 E2B IQ4_XS and its matching F16 projector directly
through llama.cpp with explicit `--mmproj`. LM Studio is not required in this
mode. See [standalone setup, configuration, and live evidence](SORA_LLAMA_CPP.md).
The LM Studio instructions below apply only when this JSON is absent or when
you explicitly pass `-DialogueModel` to bypass it. Model selection in standalone
mode is controlled by that JSON, not the LM Studio folder picker.

Open PowerShell in the SORA repository and run:

```powershell
.\Start-SORA.ps1
```

This builds the Windows components, starts Core in its own visible PowerShell window, waits for its authenticated API to become ready, and opens the full desktop app. Close the app normally and press **Ctrl+C in the Core window** to stop the server. The command uses the persistent `.local/manual-test` state, so saved Settings are reused on later starts. Dialogue defaults to the local Gemma 4 E2B model when LM Studio answers on `127.0.0.1:1234`; otherwise the offline fixture is used and a warning explains why. Delegated tasks are routed to the installed specialists at runtime, and coding writes run in an owned Git worktree below the test state instead of the source checkout.

For another standalone model/projector, edit the JSON or pass `-LlamaConfig 'C:\path\local-model.json'`. For a loaded LM Studio model instead, use `.\Start-SORA.ps1 -DialogueModel 'YOUR-LOADED-MODEL-ID'`. You can also pass `-Client Widget` or `-Port 18765` if needed. Real screen/image interpretation requires a working vision model with a matching projector, either managed by SORA or served externally.

### Native window and file questions (W4 progress, 2026-10-02)

The one-command launcher now builds and wires all four Windows helpers: native observation,
capture, press and type. Their availability is still subject to the saved static settings;
wiring a helper does not prove every model-driven action or cross-application workflow works.
With a local dialogue model, ordinary chat can use `list_windows`, `inspect_window`
(controls/text/selection), `list_files`, `search_files`, and `read_file`. Access comes from
the static **Companion access** settings; there is no per-file or per-window SORA grant.
Disabling screenshots does not disable native Windows text. Access controls are listed first
in Settings, ahead of advanced GPU/model controls.

Core also keeps a volatile identity for the last non-SORA foreground application using Windows
events (no screenshot or background model inference). When switching from an application to
the Windows SORA chat, a question such as "What is selected in the application I was using?"
can resolve that identity through a fresh window inventory, then read its current UIA selection.
The hint expires after five minutes, clears on desktop-switch events/access changes/shutdown,
and never substitutes for fresh text or permission to interact. Browser-tab handoff is not yet
supported. On 2026-10-02 the unnamed prior-application GUI test returned the fixture's selected
text `bef` using native information. Other editors may clear their selection when focus changes;
that is not a historical-selection guarantee.

Settings now includes **Perception**: native-only metadata context (default), optional
**image-on-prompt** of the recent application window, metadata switches, and automatic-perception
pause. Adaptive mode also performs optional changed-image interval interpretation, with a bounded
transient summary and foreground conversation priority. See [the settings guide](SORA_SETTINGS.md)
for prerequisites, timing, provenance and remaining cancellation limits. Access remains static;
Windows clients no longer ask for a separate
approval each time you use **Look at screen**.

Ordinary loopback-model replies explicitly disable the server's default extended thinking;
the separate memory-rationale request retains its explicit opt-in. A conversation deadline now
returns a distinct timeout explanation instead of calling a slow model unavailable. Check the
transcript before retrying and use **Dialogue timeout** in Settings if appropriate.

Try “Which windows are open?” or “Find the note mentioning meeting in C:/my/folder and read it.”
No attachment or project-root registration is needed for a readable local file. Responses show
read sources, timestamps, and partial/unsupported outcomes. Reads are bounded; PDF/spreadsheet
text adapters, cloud-only placeholders, network paths and inaccessible Windows UI remain
explicit limitations. These new reads are available only to the authenticated local owner
with local inference, not paired remote sessions or external hosted dialogue endpoints.

Restart Core after updating this checkout. An already-running Core does not hot-load new Python
code or native helper changes. Existing saved settings and personal conversation history are
preserved. Full W4 acceptance and passive foreground context are still in progress.

### Desktop avatar

Normal startup also launches the packaged Unity companion. Build it with
`scripts/build-embodiment.ps1` if `clients/unity/Builds/Windows/SORA.exe` is absent,
or pass `-NoAvatar` for a UI-only session. The full app's **3D companion** tab reports
its connection and provides Wave, Sit, Lean, Climb pose, and Stand/reset previews.
Thinking/waiting states reflect dialogue/specialist activity; these presentation
states do not authorize desktop clicks or typing.

The bundled character is **Seed-san**, credited in `clients/unity/Assets/StreamingAssets/AVATAR_LICENSE.md`.
To load your own VRM, run:

```powershell
.\Start-SORA.ps1 -AvatarPath 'C:\path\SORA.vrm'
```

Closing Core also closes its avatar. Closing a desktop client alone leaves Core
and the avatar running. Do not launch a second Core against the same state folder;
open another client with `scripts/open-manual-test.ps1` and the current port instead.
If the default port is occupied, the single launcher chooses another and prints it;
an explicitly supplied busy port is rejected.

## Advanced: start Core separately

Open PowerShell in the SORA repository and run:

```powershell
.\scripts\start-manual-test.ps1
```

The script checks `uv` and the .NET SDK, builds the current Windows capture helper, widget and full app, then starts Core in that terminal. Keep it open. Press **Ctrl+C** there when finished. Core starts with `--provider auto`, so every installed specialist is registered and routing picks one per task; when LM Studio answers, dialogue also starts on the local Gemma 4 E2B model instead of the fixture.

### Where delegated work happens

`--workspace-root` defaults to `<state root>\workspace` and is the working directory handed to Hermes,
Codex, Antigravity and Claude when they have no explicit directory of their own. Managed coding writes need an
owned Git base, so on first start the script initialises that workspace as a Git repository when it is
not already one. Write tasks therefore run in a fresh worktree under `<state root>\coding-workspaces`
and never modify the source checkout; SORA keeps the worktree plus a review artifact and never merges
it automatically.

Pass `-WorkspaceRoot C:\path\to\dir` to delegate somewhere else, or `-WriteRepo C:\path\to\repo` to
let coding writes target an existing Git repository. With `-WriteRepo`, that repository must already
be a Git repository, and its `HEAD` is the base the agent starts from.

For actual conversation and desktop/image interpretation, first load a **vision-capable** model in LM Studio and start its local server at `http://127.0.0.1:1234/v1`. Check the loaded model identifier with `lms ps --json`, then start Core instead with:

```powershell
.\scripts\start-manual-test.ps1 -DialogueModel 'YOUR-LOADED-MODEL-ID'
```

Alternatively, start with the default command, open the full app's **Settings**, paste the directory configured in LM Studio's **My Models** tab into **LM Studio folder**, and select **Scan models**. SORA lists LM Studio-indexed GGUF models whose files exist under that directory, including a vision marker where LM Studio provides one. Choose a model, save, then restart Core with the same start command to activate it. A folder of arbitrary GGUF files that LM Studio has not indexed will not be offered as loadable options; configure that folder in LM Studio or import those files there first. LM Studio's local server must be running, and either JIT model loading must be enabled or the chosen model loaded manually.

The script checks that the loopback model endpoint responds before launching Core. It does not download or load a model, alter LM Studio settings, or send private file/screen content to a remote model. A catalog **vision** marker is not a successful inference test. On 2026-09-27 this machine could load Gemma models, but saved LM Studio argument overrides disabled `--mmproj`; even tiny image requests were rejected for missing vision support. The selected uncensored E2B also reports text-only. For screen interpretation, select a vision-capable model, enable its matching projector in LM Studio, reload it, and test an image. The earlier 2026-09-26 load failure is historical evidence, not the current diagnosis.

If port 8765 is occupied, pass an alternate port to both scripts, for example `-Port 18765`.

## Advanced: open a client separately

In a **second** PowerShell window in the repository, run one of:

```powershell
.\scripts\open-manual-test.ps1 -Client Desktop
.\scripts\open-manual-test.ps1 -Client Widget
.\scripts\open-manual-test.ps1 -Client Browser
```

Run each command in its own terminal if you want multiple Windows clients open simultaneously. The desktop clients read Core's rotating owner token from the private test-state file; do not copy it into their settings. Browser mode opens `http://127.0.0.1:8765/app` and tells you where to read the owner token for the PWA's unlock prompt. Do not share that token or put it in a URL.

## Suggested test

1. Send `Hello, SORA` in Chat. With the deterministic backend, expect a fixture reply; with a loaded local model, expect a model reply.
2. In the full app's Chat tab, use **Attach file** or paste a local path beside it, enter `Summarize this file`, then send. In the expanded widget, use **Files & references → Attach file**, or paste a path and select **Attach path**, then send. SORA may read any regular local file that its Core process can read, including outside configured content roots. Choose a harmless test file first. Large files are excerpted; PDFs and other binary formats do not yet receive semantic parsing.
3. Put harmless content on the display under your cursor. Select **Look at screen** in the full app or **Look** in the widget and ask what is visible. This uses the static image-access switch with no per-request approval. It requires a working local vision model; the deterministic backend should give a clear configuration error instead of pretending to see.
4. Use **Delegate** to hand work to a specialist. SORA routes at runtime — coding and repository tasks go to Cody (Codex), research and general reasoning to Hermes or Antigravity — and an unregistered provider fails rather than silently substituting the fixture. Coding writes land in an owned worktree described above.

The explicit one-time desktop action observes the entire display under the cursor, not just SORA's window. It is owner-local and governed by static access settings; sensitive content visible on that display may be included in the local model input. Automatic image-on-prompt instead captures only the recent application window, with no whole-display fallback. Raw file/image payloads are not stored as chat messages; a model's answer may quote file content and will be stored in chat history. The test state persists across runs under `.local/manual-test`; no script removes it.

If either desktop client says **Reconnecting**, check that the Core terminal is still running and both commands use the same `-Port`. If **Look** says the model cannot view images, confirm Core was started with a loaded vision-capable `-DialogueModel`, the local model server is still running, and the newly built `windows_capture.exe` exists.
