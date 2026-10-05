# 2026-09-29T2158+0100 — Chat action hooks: walk-to-pointer + look-at-screen

Author: Deepseek V4.1 Flash (Hermes). Requested by the owner: *"could you add those hooks into
the full launch script? it's not a full launch script if not all the features are in it."*
The hooks are Core code; the launcher change is that the full launcher now brings them up and
documents them, and this entry records the live end-to-end verification through the launcher.

## What this fixes

Two refusals that were correct about the *chat door* but wrong about SORA:

1. Chat said she could not walk, because the chat motion vocabulary (`wave/sit/lean/climb/stand`)
   had no walk — even though `MOVE_TO` and the Unity locomotion existed and were verified live.
2. Chat said she could not see, because ordinary chat never attached a screenshot — the only
   image path was the explicit **Look at screen** button.

## Changes (all in the working tree, nothing committed)

| File | Change |
|---|---|
| `src/sora/contracts/motion.py` | `walk` added to the keyword set + prompt examples (`Come here`, `Walk to my pointer` → walk; `Walk around the screen`, `Can you walk?` → none). `MOTION_STATES` still maps poses only; walk is not a renderer state. |
| `src/sora/contracts/screen.py` | New one-token contract `ScreenViewChoice` (`none|screen`) + classifier prompt for the screen hook. |
| `src/sora/contracts/registry.py` | `screen-view-choice` added to public contracts; schema exported to `contracts/schema/v1/screen-view-choice.schema.json`. |
| `src/sora/providers/dialogue.py` | `ScreenViewDialogueProvider` protocol + `choose_screen_view` on the OpenAI-compatible provider (schema-constrained, temp 0, 64 tokens). |
| `src/sora/runtime/service.py` | Chat path: `walk` dispatches one authorized `MOVE_TO` to `_walk_destination()` (pointer from the capture helper, else cursor-monitor centre, else primary centre). Screen hook: a `screen` keyword triggers one capture of the cursor's display, attached to that turn's reply; capture failure is reported to the model truthfully. New `_desktop_view_ready`, `_capture_cursor_display` (shared with `dialogue_with_desktop_view`), `_walk_destination`. `allow_desktop_view` flag (owner-local only, like motion). Capability note replaces the old narrow `[CORE MOTION ROUTER]` text. |
| `src/sora/embodiment/local_player.py` | `walk_to()` (authorized MOVE_TO; refuses off-display targets) + walk-aware watcher: while travelling, pose restores are deferred so a turn-end projection push can no longer cancel the walk (the 1631 px-short bug). Travel ends on arrival (±60 px of reported position) or after 20 s. |
| `src/sora/desktop/capture.py` + `clients/windows_capture/Program.cs` | `list_monitors` now also returns the cursor point (`cursor_x/cursor_y` added to the helper reply) — the walk destination and screen capture both key off the pointer. |
| `src/sora/api/routes.py` | `allow_desktop_view=remote_scopes is None` — paired/remote chat cannot trigger capture. |
| `scripts/start-full-sora.ps1` | Header comment and startup banner now list the chat actions this launch enables (pose keywords, walk-to-pointer, look-at-screen). No new flags were needed: the script already wired the capture helper and the avatar the hooks ride on, and it rebuilds the helpers (picking up the new cursor fields). |
| `docs/runbooks/SORA_MOTION_KEYWORDS.md` | Walk row, suppression rule, chat screen-read row; launcher note corrected. |

Tests: 5 new content cases (walk dispatch + turn-end suppression; screen keyword schema; chat
capture + attach; no-capture without a screen request; remote denial; truthful failed-capture) and
one obsolete rejection case (`{"motion":"walk"}`) removed. **471 passed / 13 skipped**, ruff and
strict mypy clean.

## Live verification through the launcher (what was actually observed)

1. Old stack stopped; `.\scripts\start-full-sora.ps1 -Port 18769` started Core + all four Windows
   helpers + managed gemma-4-E2B (with mmproj) + Unity avatar + desktop GUI. `model_state: ready`.
2. Helpers on this launch: readyz 200; companion configured/running/visible; UIA observe on the
   avatar process → `status: ok`, window `("SORA","Window")`; capture 3840×2160 with dims + sha256
   re-verified.
3. **Screen hook via ordinary chat**: `What can you see on my screen right now?` → 201 in 10.7 s →
   *"The screen displays a dark desktop interface with numerous application icons and a file
   explorer visible. The background features a distinct, stylized night sky with purple and green
   cloud patterns."* That is this desktop.
4. **Walk hook via ordinary chat**: `Come here` → 201 → *"I sent a walk request to my 3D avatar
   toward your pointer. This confirms dispatch, not arrival."* Position telemetry: (90,300) →
   (94,420) → (109,820) → (124,1219) → (139,1619) → (153,1982), states `moving → … → idle`.
   The helper reports the cursor at **(153,1982)** — she stopped exactly on the pointer. Movement
   continued after the dialogue turn ended, proving the turn-end restore no longer cancels a walk.
5. Visual: capture of the region around her final position shows the avatar standing on the
   desktop at that spot (`sora_at_cursor.png` in the Hermes scratch dir).

## How the owner can test

`.\scripts\start-full-sora.ps1` (GUI opens by default). In the Chat tab:

- `Come here.` / `Walk to my pointer.` — she walks to your pointer.
- `What can you see on my screen right now?` — she describes the display under your cursor.
- Poses still work: `Wave to me.` `Sit down.` `Lean.` `Climbing pose.` `Stand up.`
- `Can you walk?` / `Walk around the screen.` are deliberately answered in words, not actions.

## Honest caveats

- The screen hook needs the capture helper **and** a vision-capable dialogue model (current
  default E2B + mmproj). With a text-only model selected, the capability note says screen viewing
  is unavailable for the turn and no capture happens.
- E2B vision is coarse: it describes scenes broadly, not fine text. Structured-first (UIA/windows)
  remains the accurate path for exact reads.
- Walk speed is 800 px/s with a 20 s watchdog; she glides (no walk-cycle animation). If the walk
  target can't be captured from the pointer, she walks to the cursor monitor's centre.
- No coordinates or speeds come from the model; only the Core computes destinations. Remote chat
  cannot trigger motion or capture.
- The running Core was restarted to load this code (old stack stopped first: uv→sora.exe→python,
  its managed llama-server, Unity player, desktop app).
