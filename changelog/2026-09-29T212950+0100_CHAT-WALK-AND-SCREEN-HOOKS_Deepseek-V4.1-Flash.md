# Chat hooks: walk-to-pointer and look-at-screen (in the full launcher)

**Date:** 2026-09-29T212950+0100 · **Author:** Deepseek V4.1 Flash
**Scope:** the two missing chat doors for features that already existed at Core level —
asking SORA in ordinary chat to walk somewhere, and asking her what is on the screen.
Plus the `scripts/start-full-sora.ps1` update and live verification through it.
Uncommitted by request (working tree only).

## Why

Sending "can you walk around?" or "can you see my screen?" in chat got correct refusals
even though walking worked via the embodiment command API and screen reading worked via the
Look-at-screen button. Root cause (established earlier today):

1. The chat motion vocabulary (`contracts/motion.py`) had only poses
   (`wave/sit/lean/climb/stand/none`) — no way to express walking, and the appending
   `[CORE MOTION ROUTER]` note told the chat model "no coordinates or physical/desktop
   effects are supported".
2. Nothing in ordinary chat ever attached a screen image; only the explicit
   `POST /api/v1/dialogue/desktop` path ("Look at screen" button) captured.

The user asked for both hooks to be wired so every working feature is reachable from the
one full-launcher command. Constraint kept throughout: the small model never supplies
coordinates, grants, or capture parameters — it only chooses one keyword; Core derives and
executes the rest under the existing capability/grant machinery.

## What changed

| File | Change |
|---|---|
| `src/sora/contracts/motion.py` | Added `walk` to the motion vocabulary. Prompt now defines walk (to the owner's pointer), adds examples ("Come here" → walk, "Can you walk?" → none), and keeps "choose none" for movement coordinates/multiple actions. `walk` is deliberately **not** in `MOTION_STATES` (it is a command, not a renderer pose). |
| `src/sora/contracts/screen.py` (new) | `ScreenViewChoice` (`{"view":"none|screen"}`) + `SCREEN_VIEW_PROMPT`: decides whether the owner's current message asks about the current screen. |
| `src/sora/contracts/registry.py` | Registered `screen-view-choice` in `PUBLIC_CONTRACTS`; exported to `contracts/schema/v1/screen-view-choice.schema.json` (and the other public schemas re-exported). |
| `src/sora/providers/dialogue.py` | New `ScreenViewDialogueProvider` protocol + `choose_screen_view()` on the OpenAI-compatible provider (schema-constrained JSON, temperature 0, 64-token cap — same form as `choose_motion`). |
| `src/sora/embodiment/local_player.py` | `LocalAvatarSession.walk_to(x, y)`: dispatches one authorized `MOVE_TO` (800 px/s, current topology revision, existing `embodiment.command` grant). New `_walk_in_progress()`: travel ends on client-reported arrival within 60 px or after 20 s. **The watcher defers pose restores while a walk is in flight** — this is the fix for the walk-cancellation bug found earlier today (a turn-end pose restore pushed a projection, the client re-hydrated, re-anchored, and killed the walk 1631 px short). |
| `src/sora/runtime/service.py` | Chat path: `allow_desktop_view` parameter (owner-local only; remote sessions denied). Motion branch now handles `walk` (Core's `_walk_destination()` picks the destination: pointer from the capture helper → cursor monitor centre → primary centre). New `_desktop_view_ready()` (capture bridge + loopback vision model) and `_capture_cursor_display()` (one-shot capture of the cursor's display, extracted from the desktop-dialogue path so both doors share it). When the screen keyword fires, the frame is attached to the normal dialogue turn (`respond_with_images`) with a truthful context note; capture failure is reported to the model ("could not be captured") rather than silently skipped. The `[CORE MOTION ROUTER]` note became `[CORE ACTION NOTE]`: poses + walk described, plus whether screen viewing is available *this turn*. |
| `src/sora/api/routes.py` | `POST /api/v1/dialogue` passes `allow_desktop_view=remote_scopes is None`. |
| `clients/windows_capture/Program.cs` | `--list-monitors` reply now includes `cursor_x`/`cursor_y` (the pointer location, same DPI-aware source as cursor-monitor selection). |
| `src/sora/desktop/capture.py` | `list_monitors()` returns `(monitors, cursor_monitor_id, cursor_point)`. |
| `scripts/start-full-sora.ps1` | Header now lists the reachable chat features; banner prints a `Chat actions` line. **No flag changes were needed** — the script already wires the capture helper (walk destination + screen capture) and the avatar (`--embodiment-player`), and it rebuilds every helper on start, so the new capture-helper fields take effect on a normal run. |
| `docs/runbooks/SORA_MOTION_KEYWORDS.md` | `walk` keyword documented (table + boundaries + the deferred-restore note); the "ordinary chat does not capture" row replaced with the new on-ask capture behaviour. |
| Tests | `tests/providers/test_motion_dialogue.py`: schema-reject list no longer includes `walk` (by design flip); new test `test_walk_keyword_dispatches_move_to_and_defers_pose_restore` (walk dispatches `MOVE_TO` to the primary centre when no bridge, the pose restore is suppressed mid-walk even across a turn-end, and returns after arrival). `tests/providers/test_local_file_and_desktop_dialogue.py`: `FixtureCaptureBridge` 3-tuple; new tests — screen keyword provider contract, chat screen question captures exactly once and attaches the frame (frame erased after), non-screen chat never captures, remote chat never classifies/captures, failed capture reported truthfully. |

## How it works now (owner-local chat)

- "Come here" / "Walk to my pointer" → `choose_motion` returns `walk` → Core samples the pointer
  from the capture helper and dispatches one `MOVE_TO`; the reply says "This confirms dispatch,
  not arrival". If clicked coordinates inside the message ("move 100 pixels right") the selector
  returns `none` — the model never sees a coordinate field.
- "What can you see on my screen right now?" → `choose_screen_view` returns `screen` → Core
  captures the display under the cursor once (same grant/one-shot/TTL path as Look-at-screen) →
  normal dialogue turn with the image attached. Chat that is not a current-screen request does
  not capture.
- Everything remains owner-local: remote paired sessions cannot trigger walk, capture, or
  classification (route now passes `allow_desktop_view=False` and the existing motion/file gates).

## Verification (all on the launcher-started stack, port 18769)

Static: 471 passed / 13 skipped (full suite); ruff clean; strict mypy clean (117 sources);
`scripts/export-contracts.py` run; launcher PowerShell parse check "parse ok"; launcher run
exit 0 with the new banner.

Live, through `scripts/start-full-sora.ps1` (old stack stopped first, helpers rebuilt):

1. **Walk hook.** Chat "Come here, please walk over to my pointer." → canned dispatch reply;
   trail from (90,300): 410→810→1210→1610→2010→2410→2810→3210→**3559**,300 in ~4 s at
   800 px/s, state `moving` → `idle`. The helper reported the pointer at x=3559 — she stopped on
   the pointer's exact column. Second request ("Come here.") with her parked at (3559,300) and
   the pointer at (3559,196): instant arrival, no jitter — correct, because Core targeted the
   pointer and Unity's placement policy (`OverlayPlacement.SafeAnchor`: 300-px-tall footprint
   must fit below the work-area top) resolves y=196 → y=300. **Not a targeting bug**: independent
   capture via the pipeline shows her rendered exactly there (feet ≈ y 300).
2. **Screen hook.** Chat "What can you see on my screen right now?" → real vision description:
   "I see a complex software interface that appears to be a code editor… panels and code blocks…"
   (the screen actually held the Hermes app, a PowerShell with the SORA API banner, and the SORA
   GUI — the mechanism works end to end; the *acuity* of the local E2B model remains the known
   weak link, same as established earlier).
3. Both exchanges are visible in the live desktop-app chat window; header "Connected · 0 active
   runs"; her rendering position in the pipeline capture matches her reported coordinates.

## Known limits / not done

- She still **glides** (no walk-cycle animation), and walk needs the avatar + capture helper.
- Screen-on-ask needs a vision-capable loopback dialogue model selected in Settings; otherwise
  the note says screen viewing is unavailable this turn (truthful, no silent failure).
- Unity clamps the destination to keep her footprint fully on-screen; the user's deferred
  constraints (lean against window/monitor borders, no floating) are not implemented yet.
- No autonomous walking; one walk per chat turn; no queueing.
- E2B vision descriptions are coarse (see above); UIA/structured reads remain the better path
  for precision.

## Probes (out of tree)

`C:\Users\oscar\AppData\Local\hermes\cache\scratch\chat_hooks_live.py`,
`walk_cursor_check.py`, `check_avatar_visible.py`, `ground_truth_screen.png`,
`avatar_visible_check.png`, `chat_hooks_live_results.txt`. No commits; working tree only.
