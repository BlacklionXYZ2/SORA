# How to use SORA (current state)

**Last updated: 2026-10-30, Opus 5.5 (ARDY: steady long idles and getting up after a fall).** This page describes what works *today* and how to use it.
Every change that alters how SORA is started, set up or used must update this page in the same
change (see [AGENTS.md](AGENTS.md)). If something here is wrong, it is a bug in this page.

For where SORA is going, read [VISION.md](VISION.md). For what V1 still needs, read [V1.md](V1.md).

## Start and stop

**Double-click SORA on your Desktop.** That starts her in full, with no console window: the
avatar, the tray icon, her local model and screen awareness. It takes about 15 seconds after the
first build. Opening it again while she runs shows her command menu. If something she needs is
missing (for example her avatar has not been built), a message says what to run, and the details
are in `.local\launch\`. To recreate the shortcut, run `.\scripts\install-shortcut.ps1`.

From a terminal it is the same as:

```powershell
cd C:\Users\oscar\Desktop\SORA
git pull                 # get the latest version
.\Start-SORA.ps1         # build, start SORA's Core, open the native app
```

- SORA appears with **no window**: her avatar on the desktop and an icon in the system tray.
  Starting again while she is running opens her command menu instead of a second SORA.
- **Open Chat:** press **Ctrl+Alt+Space** (you can change this in Appearance), or use the tray
  icon or command menu.
- **Quit:** tray icon or command menu, then **Quit SORA**. Everything closes: Core (`sora.exe`),
  her brain (`llama-server`), Laya, her avatar (`SORA.exe`), voice and the app (`SoraShell.exe`).
  Core shuts down gracefully first; anything still running after that is stopped. Other
  programs' `llama-server`s (Hermes, for example) are never touched.
- **Without the avatar:** `.\Start-SORA.ps1 -NoAvatar`. **Headless (no app):** `.\Start-SORA.ps1 -NoClient`.
- `.\Start-SORA.ps1 -Client Desktop` opens the older full app. It still works but is frozen (no
  new features).

## First-time setup

1. **Choose her brain model.** Open **Settings** (tray icon or command menu). It opens on
   **Models**.
   - The card at the top shows the model she is using now and whether it is loaded.
   - Click **Change model** and pick the GGUF file. The planned brain is
     `Models\Unsloth\gemma-4-E4B-it-Q4_K_M-GGUF\gemma-4-E4B-it-Q4_K_M.gguf`.
   - Its **vision projector** is found automatically beside it.
   - Click **Save and reload model** in the bar at the bottom. The card says **Loaded** when
     she is ready.
   - Other settings work the same way: change them, then **Save** (or Ctrl+S). The bar says if a
     change needs the model to reload or SORA to restart. **Discard** undoes unsaved changes.
   - Ignore **External server** unless you set General → **Model source** to an external server
     such as LM Studio.
2. **Let her see your screen.** Settings → **Vision** → perception mode **image-on-prompt**.
   - Every message you type or say then includes a picture of your **whole desktop, both
     monitors**, scaled down. She calls it your screen or desktop, never "the image you sent".
   - Small text can be blurry at that size. When she needs detail ("what does this error say?",
     "look closer"), she takes a full-size picture of one window: the one you name, or else the
     one you are using or used last before switching to SORA. Chat shows "Looked at the desktop"
     and "Looked closer at a window".
   - **Vision detail** (top of Settings → Vision): **Low**, **Medium** (the default) or **High**.
     It sets how many tokens each image may use in her model (280, 1,024 or 2,048), with a
     matching batch and context length. Higher detail means slower replies and more context and
     GPU memory, but she reads your screen more reliably and guesses less. Saving reloads the
     model. Measured with E4B on this PC, one desktop picture took 3.6 s at Low, 4.1 s at Medium
     and 6.5 s at High.
   - Changing the image token budget, physical batch (Performance) or context length (Models)
     by hand shows **Custom**. Move the slider to use a level again. Settings saved before
     2026-10-08 with untouched defaults move to Medium; hand-tuned ones become Custom.
   - Her own Chat window and avatar can appear in the desktop picture.
   - Pictures are saved only when she remembers a moment (with that memory, on this PC; see
     "Her character, goals and memories"). **Pause** in Settings → Vision stops them.
   - Settings created before 2026-10-05 keep their old mode until you change it.
3. **Voice (once):** run `.\scripts\setup-local-voice.ps1`, or start with `.\Start-SORA.ps1 -SetupVoice`.
   It now also downloads the **fast voice model** (325 MB, once). On this PC she starts speaking
   about ten times sooner than with the old int8 model, so run it again even if voice already
   works. `-NoFastVoiceModel` skips the download.
4. **Rebuild her avatar (once, and after a `git pull` that changes the avatar):** quit SORA, then
   run `.\scripts\build-embodiment.ps1`. The avatar program is not rebuilt by `Start-SORA.ps1`, so
   an old build keeps running without newer moves and mouth shapes. Afterwards she walks, runs
   and sits on request, and her mouth forms A, E, I, O and U shapes from her voice.

   **Her look:** she wears **Alice** by default (from 2026-10-11). Credit: "Alice", Zenless Zone
   Zero; original model by miHoYo, VRM by Niko on VRoid Hub.
   - The file is `.local\avatars\Alice.vrm`. It is kept out of git because her licence forbids
     sharing or editing the file, so on another PC copy it there yourself.
   - **To change her avatar:** Settings → **Appearance** → **Avatar model (VRM)**. Pick a `.vrm`
     file (VRM 0.x or 1.0), **Save**, then quit SORA and start it again. No rebuild is needed.
   - Clear the box to use the built-in Seed-san. She also uses Seed-san if the file is missing.
   - **Hair, clothing and accessories move differently** (from 2026-10-15).
     - When her avatar loads, each moving part is sorted into hair, clothing (skirt, coat, tie)
       or an accessory (tail, ears, props, soft tissue), and each kind gets its own weight,
       stiffness and damping.
     - Parts that came with no collision get collision with her body, so they don't pass
       through her.
     - Her player log lists what each part was sorted as ("Secondary part: …").
     - **If one is wrong,** create `.local\avatars\Alice.vrm.parts.txt` (the avatar's file
       name plus `.parts.txt`). Put one line per part, for example
       `41.joint_Skn_Tail_01 = hair`, using `hair`, `clothing` or `accessory`, then restart
       SORA.
   - **Her body is physical** (from 2026-10-17). Her animation (standing, poses, pointing,
     looking) drives motors in a simulated body with real weight, so gravity, inertia and the
     surface she stands on act on her.
     - Walking lifts her feet and matches her stride and step rate to her speed. Running
       (from 2026-10-21) uses shorter foot contacts with both feet briefly off the ground. When
       she stops she takes a few steps on the spot to bring her feet under her.
     - Picked up, she hangs loosely from the point you grabbed (her head, an arm, a foot), not
       from her hips (from 2026-10-21). Dropped, she falls at real gravity for her size; if she
       lands hard she falls over physically, comes to rest, and gets back up where she landed
       (the getting up is a placeholder until her motion model learns it). A fall that hasn't
       ended after about 20 seconds ends anyway, so she can't get stuck lying down.
     - Her collision shape follows her mesh, including rigid accessories such as a robot arm,
       so her body rests on the taskbar rather than sinking into it. Hair and loose clothing
       can still dip into the floor.
     - These changes reach the avatar program only after `.\scripts\build-embodiment.ps1`.
   - **Her size:** she stands 500 physical pixels tall on every monitor (from 2026-10-16; 300
     before), whatever its scaling.
   - **Her eyes move and she blinks** (from 2026-10-16).
     - She looks at you when nothing else has her attention, glances away now and then, and
       often looks away as she starts to speak. When she looks at a window or control, her eyes
       get there first; her head turns only for bigger shifts. Her eyes stay on what she's
       looking at while her head or body moves.
     - She blinks about 17 times a minute, more while talking and less while concentrating.
     - It uses each avatar's own eye settings, so any VRM works: eye bones (Alice) or look
       expressions (Seed-san).
   - **Diagnostic switches** (for tracking down a problem; start SORA from PowerShell):
     `$env:SORA_EYE_RIG = "0"` keeps her eyes still, and `$env:SORA_SECONDARY_COLLIDERS = "0"`
     turns off the body collision added for hair and clothing. `$env:SORA_PHYSICS_BODY = "0"`
     brings back her old posed body and preset fall. `$env:SORA_PHYSICS_HELP` sets how much
     non-physical help her body gets: `full`, `no-exempt`, `realistic` (the default: real muscle
     strength plus a balance helper at her hips) or `none` (she can't yet balance on her own).
     A value it doesn't recognise falls back to `realistic` and writes a warning to the avatar's
     log. Then run `.\Start-SORA.ps1`.
5. **Decision layer (once, optional):** run `.\scripts\setup-decision-layer.ps1`. It downloads
   Laya (about 430 MB) and its GPU runner (18 MB) into `.local\decision`. Laya is a small, fast
   model that picks which kinds of tools her brain sees for each message (about 20 ms on the
   GPU). Settings → **Models** → **Decision layer**:
   - **shadow** (default) logs its choices for later training but changes nothing;
   - **enforce** offers her only the kinds it chose, which should make tool use more reliable;
   - **off**.

   If its files are missing or it fails, she simply sees every tool, as before. To train it on
   your own messages later, follow [docs/runbooks/TRAINING_LAYA.md](docs/runbooks/TRAINING_LAYA.md).
6. **Free the GPU** before starting SORA. Unload LM Studio's model, for example. SORA's brain and
   LM Studio's model do not both fit comfortably in 16 GB.

## Talking to her

- **Typing:** type in Chat and press **Enter** to send. **Shift+Enter** adds a new line, and
  **Stop** cancels her reply.
- **Voice:** in Chat, click the **microphone** once to start voice. A small dot shows its state:
  amber while loading, green when ready.
  - **Hold the microphone** (mouse, or Space when it is selected) while you speak, and let go to
    send. It turns red while it is listening.
  - Switching to another window while holding throws the recording away.
  - **Talk without the button (always-on listening, the default):** voice starts with SORA and
    Chat's microphone is blue: she is listening. (Settings → **Audio** → **Listening** →
    **press** brings back hold-to-talk.) Say her name anywhere in a sentence ("Sora, what's this?", "what do you think,
    Sora?"). For about 8 seconds after she replies you can keep talking without her name
    (**Keep listening after she replies**). Saying her name while she talks interrupts her.
    - **To make her stop talking,** say "stop", "Sora, stop", "be quiet", "hold on" or "never
      mind". She goes quiet without starting a new reply. ("Stop it" or "cancel it" stops a
      running agent task instead.)
    - She is told to expect her agents' names (Claude, Cody, Hermes, Aggie and your custom
      agents' nicknames), so "Claude" isn't heard as "cloud".
    - Speech not meant for her is heard and ignored; nothing is sent or saved. A recording is
      saved only with a moment she chooses to remember.
    - **Click the blue microphone to stop listening**; the microphone closes until you click it
      again or restart SORA. Turning **Enable voice features** off in Settings stops it starting.
    - If she mishears her name, add spellings under **Names she answers to** (for example
      `sora, zora`).
    - With speakers rather than a headset she hears her own voice; she ignores it unless it
      contains her name in words she isn't saying herself. A headset works best.
  - **She hears your voice itself** on Gemma 4 E2B and E4B (their vision projector also has
    an audio encoder), not only the transcript, so tone and mis-transcribed words reach her.
    Settings → Audio → **Voice to the brain** → **transcribe** sends only the text.
  - The **Voice** window (right-click the microphone in Chat, or use the tray) shows the
    microphone, the audio devices Core last reported and a big **Hold to talk** button. Hold it,
    or Space, in the same way. She answers out loud with her mouth moving. Holding again interrupts her.
  She starts speaking her first sentence while she is still thinking up the rest, usually
  about 2 seconds after you let go. Spoken answers are kept short (one to three sentences);
  ask "tell me more" for detail.
- **Poses:** "sit down", "lean", "climb", "stand up". She has **no wave**. What used to be
  called "wave" only walked her on the spot, so it was removed; ask her to walk instead.
- **Walking and running:** she can walk or run to your pointer ("come here"), to the ground
  beneath a window ("go over to Spotify"), or to the left, centre or right of your main monitor,
  the monitor your pointer is on, or the other monitor. She can also take a pose when she
  arrives ("run to the right of the screen and sit down"). She picks the destination and Core works
  out the exact spot, so she never guesses coordinates. Moving never clicks or changes a window.
- **Looking and pointing:** "look at the play button", "point at it". She looks at or points to
  a control she has inspected in a window.
- She cannot yet press buttons or type in other apps from chat.
- **Memory:** she remembers things you tell her across restarts. Browse, search, correct or
  forget what she remembers in **Memory** (tray icon or command menu).

## Her character, goals and memories

- **Her character** is yours to write: copy `identity\character.template.md` to
  `identity\character.md` and answer its questions in your own words, then restart SORA. She
  can't change it. Until you write it, her identity is only the short policy files.
- **Things you ask her to always or never do** ("from now on keep answers short", "call me
  Oz") are kept as standing instructions and shown to her on every turn, not only when relevant.
  If she doesn't choose to remember something herself, a quick second check after her reply
  catches most facts she missed.
- **How she remembers:** when you tell or show her something worth keeping, she writes a short title
  and a description of the fact ("Favourite colour": "The owner's favourite colour is now green, not
  teal."). The memory keeps the whole moment with it: your exact words, her reply, what she read,
  the pictures she saw (the desktop, a closer window, images you attached) and, when you spoke, your
  voice recording. Pictures and recordings that turn out not to relate to the memory are deleted
  rather than kept. The rest are stored in `.local\manual-test\memory\entries\` on this PC.
  **Forgetting a memory in Memory deletes its pictures and recording too.**
- **Her memories** carry the date they were made. Besides what you tell her, she can keep her
  own thoughts ("I enjoyed planning the trip"); they are ordinary memories, shown to her as *her*
  earlier thoughts, never as things you said, and appear in Memory like any other.
- **Her goals** are hers. She changes them when she **reflects**: she looks at what she has
  remembered since last time, notes progress on her goals, and may add, reword, achieve or drop
  one (with a reason; nothing is erased). To ask her to reflect now:
  `.\scripts\reflect.ps1` while SORA runs. Read her goals, with start and end dates and
  progress, in `.local\manual-test\self\goals.md`. Reflection isn't automatic yet.
- **The memory manager** (Settings → Memory → **Memory manager**) uses a small embedding model
  (EmbeddingGemma 2, about 0.75 GB of video memory with pictures and voice; it starts with
  SORA) to read each
  memory and its pictures and voice. She can then find
  memories by meaning, link related ones, and notice repeats and updates ("my favourite colour
  is now green"). It starts with SORA, a few seconds after the brain.
  - **on** (the default): her replies see the memories most relevant to what you said ("is
    there anything I should avoid eating?" finds your peanut allergy), and recent ones fill any
    spare places. **shadow**: her replies see memories that share words with your message and
    your most recent ones, and what recall by meaning would have chosen is recorded for
    comparison. **off**: not used. Without the embedding model, memories sharing words with
    your message still come first.
  - It never deletes a memory or marks one replaced by itself. It records those suggestions
    until the Memory window lets you review them.
  - Its decisions are logged for training in `.local\manual-test\memory\decisions\` (memory
    IDs and numbers, never the text). To see whether there is enough to train its small
    layers: `uv run python scripts/memory/train_layers.py`. Nothing is trained until you add
    `--train`. Guide: [docs/runbooks/TRAINING_MEMORY_LAYERS.md](docs/runbooks/TRAINING_MEMORY_LAYERS.md).
  - Setup, once, if the model files are missing: `.\scripts\setup-memory-embedder.ps1`.

## Her agent colleagues

SORA hands harder work to hosted agents and keeps chatting while they work:

| Agent | Name | Found when installed |
|---|---|---|
| Codex | **Cody** | `codex` on PATH |
| Hermes | **Hermes** | `hermes` on PATH |
| Antigravity | **Aggie** | `agy` on PATH |
| Claude Code | **Claude** | `claude` on PATH |

- **Ask naturally:** "ask Cody to look at this", "have Hermes research…". Naming one agent is
  clearest. If you name two, she asks which one you mean.
- **When an agent finishes, fails or is cancelled, she tells you in Chat.** The line in
  brackets underneath is Core's own record of what happened.
- **Follow or cancel work** in **Activity** (tray icon or command menu, or click a task chip in
  Chat), or type or say "cancel that task" or "cancel Pip's task". With one task running, "that"
  means it; with several, she asks which agent.
  - Activity lists the agents' work on the left.
  - For each task it shows your request, SORA's brief to the agent and the agent's own report:
    files changed, commands run, warnings, and anything that failed.
  - **Cancel task** stops the agent completely, after you confirm.
  - **Send instruction** tells a running agent something more.
- **Project work:** Cody, Aggie and Claude work directly in the project folder you select.
  Claude and Aggie run without permission prompts, by your decision.
- **Custom agents:** Settings → **Models** → **Agents · Custom agent 1–4**. Enable a slot and give
  it a nickname, spoken aliases (for example "pip, pippa"), a protocol and either a port
  (OpenAI-compatible, such as LM Studio on 1234) or a command (Agent Client Protocol). Restart
  SORA, then ask for it by nickname ("ask Pip to …"). Chat-only custom agents cannot work in a
  project folder; they always use the model you configured for them.

## The glass windows

Chat, Settings, Activity, Voice, Agents, Project paths, Memory, Motion and Appearance are the new
see-through windows that match the concept images. Open any of them from the tray icon or the
command menu. The note board, Content, Integrations and the command menu are still the older
style.

- **Chat:**
  - Enter sends, and Shift+Enter adds a new line. **Stop** cancels her reply.
  - The paperclip attaches up to three files. The microphone starts voice, and then you hold it
    to talk (see Talking to her). Right-click it for the Voice window.
  - Her lists, **bold** words and code are formatted.
  - Small chips under her reply show what Core recorded for that turn:
    - "Looked at the window" or "Read 2 sources": click to see the detail;
    - "Used 1 memory": click to see which memories; **Show** opens Memory on that exact memory;
    - "Asked Cody · Working": the agent task this message started, with its current state;
      click to open Activity on that exact task.
- **Settings:** categories on the left. **Models** is described under First-time setup.
  **Appearance** chooses her avatar; its **Text size, Chat shortcut and placement…** button opens
  the Appearance window. **Models** has buttons for the Agents and Project paths windows, above
  the agent colleagues.
  - **Change model** opens the file picker in the current model's folder.
- **Voice:** the microphone and voice state, the dialogue model, **Hold to talk** (mouse or
  Space; letting go sends, and switching away throws the recording away), **Stop speaking**
  (she stops talking), **Stop voice response** (stops the whole reply), **Close audio worker**,
  and the audio devices Core last reported. Copy a device key into Settings → Audio to use it.
- **Agents:** the agents SORA can hand work to, their models and what each can do.
  **Refresh models** asks each agent for its current model list. To give an agent a task
  yourself, pick the agent (or automatic), model, effort and project folder, describe the work
  and press **Start**; you confirm first. If sending fails, **Retry exact submission** sends the
  very same request again rather than starting a second task. **Open in Activity** follows it.
  You can also describe what each model is for, which SORA uses when choosing one.
- **Project paths:** which project folders an agent has reserved for writing, and what SORA
  recorded about files there. **Recheck stopped writers** (after you confirm) asks Core to
  release reservations whose writer has really stopped. It never forces anything open.
- **Memory:** **Overview** and **Search** list what she remembers, newest first, 50 at a time;
  filter by words, state (active, expired, replaced), project and scope. Selecting one shows
  exactly what Core holds and the evidence it came from (**Open** opens that file). **Correct**
  replaces a memory with your wording; **Forget** removes it after you confirm. When SORA shows
  you a memory, Memory opens on it with a glow around it. The graph view comes later, once
  Core records real links between memories.
- **Motion:** which motion model moves her body. Open it from the tray (**Motion / her motion
  model**), the command menu, or Settings → **Motion** → **Choose her motion model…**.
  - **Choose one of three sources:**
    - **Algorithmic**, her built-in poses and gait: the default and the fallback;
    - **ARDY (NVIDIA)**, a real-time motion model run on the GPU;
    - **Custom trained**, one of SORA's own versions (v1 to v4) at a size that has been trained.
      Planned sizes are shown greyed out.
  - **ARDY options:** precision (fp16 uses less video memory; fp32 is cleaner at rest) and
    diffusion steps (4 is the real-time setting on this PC).
  - **The right-hand side** plays a stick-figure preview of motion the model really generated,
    and shows how it measured beside real motion capture.
  - **Save**, then **Reload motion model** (in the window's banner) applies it at once, without
    restarting SORA. Core stops the old model and starts the new one. While it loads (about 26
    seconds for ARDY on this PC, measured once) she keeps moving by herself, and her last 3
    seconds are passed to the new model so it carries on from what she was doing. The banner then says what is moving her, or why the model
    couldn't start (she keeps the algorithmic system if it fails).
  - **What ARDY is told:** what she is doing (standing, walking or running at the speed SORA
    moves her, sitting, leaning or climbing); her emotion isn't passed on yet. Her physics, falls
    and being picked up stay as they are, and SORA still decides where she goes and which way she
    faces. It needs motion-lab's `ardy-runtime` set up; Core starts it on the GPU.
  - **Standing about and getting up with ARDY (since 2026-10-30):** after she has stood still
    for about 2 seconds, ARDY is held near that pose, so she can idle for minutes without
    drifting (before, she started flailing and spinning after about a minute). If she ends up
    on the ground, ARDY gets her up within about 3 seconds.
    Custom trained versions can be saved but can't drive her yet: only ARDY runs live so far.
  - **Where the list comes from:** the models listed come from motion-lab (a `motion-lab` folder
    beside SORA's, or Settings → Motion → motion-lab folder). After training or evaluating
    something there, run `.venv\Scripts\python tools\motion_catalog.py` in motion-lab to update
    the list.
- **Appearance:** panel text size, reduced motion, the Chat shortcut, compact Chat, pinning
  Chat on top, and **Reset panel placement**. Each setting says which windows it affects. These
  stay on this PC; they are not Core settings.
- **Quitting with unsaved work:** if Settings, Appearance, a memory correction, or a task or
  model description typed in Agents is not saved yet, SORA names the window and asks before
  throwing it away. While a recording, a task start or a memory change is still being sent, Quit
  waits and shows that window instead.
- **See-through glass** needs Windows' **Transparency effects** on (Settings → Personalisation
  → Colours). When it is off, the windows use solid dark glass.
- **Blur style:** to compare, start with `-PanelBackdrop Accent`. The default is `System`,
  Windows 11's own acrylic, and `None` is solid glass.
- **The old windows:** to go back for one run, quit SORA and start it with
  `.\Start-SORA.ps1 -ClassicPanels`. Please say what made you go back.
- **Screenshots** beside the concept image: run `.\scripts\capture-panel.ps1` (Chat), or
  `.\scripts\capture-panel.ps1 -Title "SORA · Settings" -Concept 05-settings.jpg`. The other
  titles are "SORA · Activity", "SORA · Voice", "SORA · Agents", "SORA · Project paths",
  "SORA · Memory" (concept `04-memory.jpg`) and "SORA · Appearance". Files go to
  `.local\panels-review\`.

Memory chips only appear for messages typed in this Chat. Spoken turns show their reply, but not
which memories it used.

To preview the pages in an ordinary browser (no glass, for design review):
`uv run python scripts\panels-dev-server.py --token-file .local\manual-test\private\sora-api-token`,
then open <http://127.0.0.1:8790/chat/>, or `/settings/`, `/activity/`, `/voice/`, `/agents/`,
`/paths/`, `/memory/`, `/appearance/` or `/gallery/` on the same address. Things only the app can
do (opening another window, file pickers, Appearance) say so in a browser.

## Known limits right now

- **Not yet tested end to end on the real model:** voice, the avatar, screen answers, choosing
  agents by name in conversation, and memory across restarts. This is the
  [V1 acceptance test](V1.md#how-to-run-the-acceptance-test).
- **The new Voice, Agents, Project paths, Memory and Appearance windows** were checked in a
  browser against a test Core, not yet inside SORA's app on Windows. If one misbehaves,
  `.\Start-SORA.ps1 -ClassicPanels` brings back the older windows.
- **Task routing misses "not".** "Don't edit files" can be read as a request to edit files,
  so phrase requests positively for now.
- **Not built yet:** pressing or typing in other apps from chat, Automations, the memory graph
  view, keeping images and audio with memories, desktop notes and pings, and the learned motion
  model.

## When something goes wrong

| You see | Do this |
|---|---|
| Every SORA window says Core is unreachable, or "Core returned 404" | Something else is using SORA's port. The launcher now picks a free one (8766–8775) and remembers it, but a SORA started before this fix keeps the old address: **Quit SORA** from the tray and start it again |
| "Model load failed (OSError)" in Settings | The GPU is probably full. Close other model apps and click **Reload model**. A busy model port is no longer a cause: SORA moves to the next free port (18771–18790) by itself |
| "Could not rebuild … (is it open?)" while starting | Harmless. An old SORA window was open, and SORA starts anyway |
| Start fails with "Build the 3D companion…" | Run `.\scripts\build-embodiment.ps1`, or start with `-NoAvatar` |
| SORA says "Which project?" | Set the agent's project folder in Settings → **Tools**, or choose one when delegating |
| Anything else | Check the newest file in `changelog/` and the Activity window, then ask an agent with the error text |
