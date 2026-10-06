# How to use SORA (current state)

**Last updated: 2026-10-06, Opus 5.5.** This page describes what works *today* and how to use it.
Every change that alters how SORA is started, set up or used must update this page in the same
change (see [AGENTS.md](AGENTS.md)). If something here is wrong, it is a bug in this page.

For where SORA is going, read [VISION.md](VISION.md). For what V1 still needs, read [V1.md](V1.md).

## Start and stop

```powershell
cd C:\Users\oscar\Desktop\SORA
git pull                 # get the latest version
.\Start-SORA.ps1         # build, start SORA's Core, open the native app
```

- SORA appears with **no window**: her avatar on the desktop and an icon in the system tray.
  Starting again while she is running opens her command menu instead of a second SORA.
- **Open Chat:** press **Ctrl+Alt+Space** (you can change this in Appearance), or use the tray
  icon or command menu.
- **Quit:** tray icon or command menu, then **Quit SORA**. This also stops the Core and the model
  it started.
- **Without the avatar:** `.\Start-SORA.ps1 -NoAvatar`. **Headless (no app):** `.\Start-SORA.ps1 -NoClient`.
- `.\Start-SORA.ps1 -Client Desktop` opens the older full app. It still works but is frozen (no
  new features).

## First-time setup

1. **Choose her brain model.** Open **Settings**, then **Models** in the list on the left.
   - Under **Brain (local model)**, click **…** beside **Brain model file (GGUF)** and pick the
     model. The planned brain is
     `Models\Unsloth\gemma-4-E4B-it-Q4_K_M-GGUF\gemma-4-E4B-it-Q4_K_M.gguf`.
   - Its **vision projector file** is found automatically beside it.
   - Click **Save settings**, then **Reload model**.
   - Ignore **External server** unless you set Settings → General → Model source to an external
     server such as LM Studio.
2. **Let her see your screen.** Settings → **Vision** → perception mode **image-on-prompt**. Your
   screen is then sent with every message you type or say. Settings created before 2026-10-05
   keep their old mode until you change it.
3. **Voice (once):** run `.\scripts\setup-local-voice.ps1`, or start with `.\Start-SORA.ps1 -SetupVoice`.
4. **Free the GPU** before starting SORA. Unload LM Studio's model, for example. SORA's brain and
   LM Studio's model do not both fit comfortably in 16 GB.

## Talking to her

- **Typing:** type in Chat and press **Enter** to send. **Shift+Enter** adds a new line, and
  **Stop** cancels her reply.
- **Voice:** open **Voice / microphone** (from Chat, the tray or the command menu), click
  **Start voice** and wait for **Ready**. Then **hold Hold to talk** (or Space) while speaking,
  and release to send. She answers out loud with her mouth moving. Holding again interrupts her.
- **Poses:** "wave", "sit down", "lean", "climb", "stand up".
- **Walking and running:** she can walk or run to your pointer ("come here"), to the ground
  beneath a window ("go over to Spotify"), or to the left, centre or right of your main monitor,
  the monitor your pointer is on, or the other monitor. She can also take a pose when she
  arrives ("run to the right of the screen and wave"). She picks the destination and Core works
  out the exact spot, so she never guesses coordinates. Moving never clicks or changes a window.
- **Looking and pointing:** "look at the play button", "point at it". She looks at or points to
  a control she has inspected in a window.
- She cannot yet press buttons or type in other apps from chat.
- **Memory:** she remembers things you tell her across restarts. Browse or correct what she
  remembers in **Memory / browse**.

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
- **Follow or cancel work** in **Activity**, or say "cancel Cody's task". Cancelling stops the
  agent completely.
- **Project work:** Cody, Aggie and Claude work directly in the project folder you select.
  Claude and Aggie run without permission prompts, by your decision.
- **Custom agents:** Settings → **Models** → **Agents · Custom agent 1–4**. Enable a slot and give
  it a nickname, spoken aliases (for example "pip, pippa"), a protocol and either a port
  (OpenAI-compatible, such as LM Studio on 1234) or a command (Agent Client Protocol). Restart
  SORA, then ask for it by nickname. Chat-only custom agents cannot work in a project folder.

## Known limits right now

- **Not yet tested end to end on the real model:** voice, the avatar, screen answers, choosing
  agents by name in conversation, and memory across restarts. This is the
  [V1 acceptance test](V1.md#how-to-run-the-acceptance-test).
- **Task routing misses "not".** "Don't edit files" can be read as a request to edit files,
  so phrase requests positively for now.
- **Not built yet:** pressing or typing in other apps from chat, Automations, the memory graph,
  desktop notes and pings, the decision layer, and the learned motion model.

## When something goes wrong

| You see | Do this |
|---|---|
| "Model load failed (OSError)" in Settings | Another program may hold the model port, or the GPU is full. Close other model apps and click **Reload model** |
| "Could not rebuild … (is it open?)" while starting | Harmless. An old SORA window was open, and SORA starts anyway |
| Start fails with "Build the 3D companion…" | Run `.\scripts\build-embodiment.ps1`, or start with `-NoAvatar` |
| SORA says "Which project?" | Set the agent's project folder in Settings → **Tools**, or choose one when delegating |
| Anything else | Check the newest file in `changelog/` and the Activity window, then ask an agent with the error text |
