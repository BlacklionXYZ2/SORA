# Launch: Core's port was held by another app; live check of her size and eyes

Model name: **Opus 5.5**. Checkpoint **2026-10-17 09:15:00 +01:00**, Europe/London. Status:
**SORA running; no code changed**.

## The shortcut only opened the app

The owner reported that the Desktop shortcut started only the app. Cause:
- port **8765**, which Core uses, was held by an unrelated app ("Videos Explorer",
  `python run.py`, started 2026-10-16 07:41);
- the host found the port occupied, tried to attach to it as an existing SORA, failed, and
  stopped before launching Core. So Core, her model and the avatar never started.

The host says so only in its status line ("Startup/connection not confirmed…"), which doesn't
name the port or the program. Unrelated to the eye rig and height changes.

At the owner's request:
- stopped that process (its PowerShell window then exited by itself);
- closed the stranded host, which had launched nothing;
- started SORA the way the shortcut does (`scripts/launch-sora.ps1`, profile
  `.local/manual-test`).

## Live check, owner's profile, 2026-10-17 09:03 to 09:10

- Running: Core (listening on 8765), `llama-server`, the avatar (`SORA.exe`) and the app.
- Avatar log: Alice loaded with no exceptions; her moving parts were classified as before.
- Screenshot: she stands on the primary monitor's taskbar, about 500 physical pixels tall.
- Blinking, measured on screen from the brightness of her eye area: 5 blinks in about 22 s,
  roughly 14 a minute. Sampled at about 13 frames a second, so a short blink can be missed. An
  enlarged frame shows her eyes fully closed mid-blink.
- **Not checked:** her eye movements (Alice's eye bones turn at most 10°, too small to judge at
  this capture size), eye-head coordination during a commanded look, and how natural it looks.
  Those need the owner's eyes.

Nothing committed.
