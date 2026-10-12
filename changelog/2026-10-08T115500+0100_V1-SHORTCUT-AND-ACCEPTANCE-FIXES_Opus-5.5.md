# Desktop SORA shortcut, and fixes found running the V1 acceptance steps live

Model name: **Opus 5.5**. Checkpoint **2026-10-08 11:55:00 +01:00**, Europe/London. Status:
**implemented, component-tested, and checked live on E4B in an isolated profile.** It is not V1
acceptance: that is the owner's own run, with real speech. The owner asked: "let's finish v1 then
and could you create a shortcut that loads up SORA in full as the user experience intends? …
don't boot it with the blue sora screen". This moves V1 acceptance steps 1 and 4–8 forward.

## Shortcut

- New `scripts/launch-sora.ps1` is what the shortcut runs.
  - It runs PowerShell hidden, checks that `uv`, `dotnet` and the built avatar are present, and
    then runs `Start-SORA.ps1` (the windowless host, Core, the managed model and the avatar).
  - Failures appear in a message box and in `.local/launch/launch-<date>.log`, instead of
    vanishing with a hidden console.
  - `-StateRoot` and `-Port` exist only for testing on isolated profiles.
- New `scripts/install-shortcut.ps1` creates `Desktop\SORA.lnk`.
  - The shortcut uses `-WindowStyle Hidden`, runs minimised, and uses the new `assets/sora.ico`
    (a generated blue sphere with an "S").
  - The script refuses to replace a shortcut it did not make.
- There is no demo backdrop. It was only ever a recording aid in my scratch scripts.

## Fixes found by running the acceptance steps (isolated profile `.local/shortcut-qa-20261008`)

1. **Spawn position** (`OverlayPlacement.HomeAnchor`, `SoraEmbodimentBehaviour.Hydrate`).
   - With no saved position, she kept the default origin, which a clamp turned into (90, 300):
     high on the top-left, so she fell across the sky.
   - She now first stands on the primary monitor's work-area floor, a fifth in from its right
     edge.
   - The Unity player was rebuilt.
2. **Movement follows the owner's words** (new `runtime/move_intent.py`).
   - Pace is run only when the owner says run, hurry and the like.
   - The arrival pose is used only when the owner names it. E4B had sent "run" as a walk and
     added an unrequested wave.
   - "The other side of the screen" is now the far side of the monitor she is standing on. It
     used to be the pointer's monitor.
3. **Memories with automatic screen images** (`service._dialogue`).
   - Remembering ran only on turns without images. With image-on-prompt, every turn has one, so
     nothing was ever remembered. This is also why the "Used 1 memory" chip was missing in video 2.
   - Turns with automatic images (but no owner attachments) may now store the owner's words; her
     reply is then kept out of the stored reason.
   - Owner-attached files or images still rule a turn out.
4. **Hand-off names the agent** (`repository.submit`): "I've asked Pip to take this on. It's
   queued, not completed yet…", replacing "with custom-1".
5. **Cancel from typed chat** (new `runtime/chat_cancel.py`, called from the board-command path).
   - "Cancel that task" or "cancel Pip's task" cancels deterministically. Several running tasks
     lead to a question.
   - Negated phrasing and ordinary chat are left alone.
   - The router's pronoun targets now include "that", "this" and "the task".
6. **Pointing and looking at controls.**
   - Observation trimming now drops Desktop previews, then agent defaults, then memory previews,
     and keeps the window inventory longest. The inventory had been trimmed first.
   - A first repeated read gets a hint naming windows from the owner's message, instead of
     ending the turn.
   - The owner's verb decides look or point (E4B answers "look at" with point).
   - The prompt now has an explicit three-step recipe.
   - New trace `companion.read_turn` records the offered and chosen operations; it is how this
     was diagnosed.

## Verification

- **Fixture/component:**
  - `.\scripts\verify.ps1` ran ruff, mypy (317 files), pytest (1052 passed, 25 skipped, 4
    xfailed) and the panel tests (8 and 33 passed), exit 0.
  - `dotnet test`: 405 passed.
  - New tests are in `tests/runtime/test_move_intent.py`, `tests/runtime/test_chat_cancel.py`,
    `test_companion_reads.py` (trim order, the repeat hint, the repeat bound) and
    `test_companion_presentation.py` (the owner's verb).
  - Also new: `test_automatic_screen_images_do_not_stop_remembering`, and the C# test
    `FirstAppearanceStandsOnThePrimaryTaskbarNotTheTopLeft`.
- **Live, isolated profile, E4B, launched with the shortcut's exact command:**

  | Step | Result |
  |---|---|
  | 1 Launch | Ready in 13–15 s, with no visible console. A second launch opened the command menu, and one host stayed running. |
  | 4 Screen | "What am I looking at?" described both monitors (11 s). |
  | 5 Move | Wave, sit, run to the other side and wave, walk to the Antigravity window, back left and sit: all dispatched, positions read back. |
  | 5 Indicate | After the fixes, point and look at named Antigravity buttons worked 3 of 3 each. Before them, 0 of 2, then 1 of 2. |
  | First appearance | (3071, 2087), on the main monitor's taskbar. |
  | Memory | "Remember … teal" stored a memory (`memory.created`), recalled after a full restart. |
  | 6/7 Delegate | Pip (a local stand-in agent) named in the hand-off, result reported in her words. "Cancel that task" ended a task as `cancelled`. |
  | 8 Settings | Speech speed 1.15 saved through Core and still active after a restart. |
  | Voice | Started and reached "ready" with the owner's devices listed, then stopped. No speech was tried. |

- **Owner's profile** (`.local/manual-test`, with permission given by this request):
  - Settings were backed up to
    `.local/backups/manual-test-sora-settings.before-v1-setup-2026-10-08.json`.
  - Then changed: model E2B → E4B with its projector, and perception native-only →
    image-on-prompt. Vision detail moved to Medium through the existing migration.
  - The real Desktop shortcut started it: Core on 8765, E4B loaded, 1,024 image tokens, avatar on
    the taskbar.
  - It was left running for the owner. No messages were sent in the owner's conversation.
- **Not run:**
  - real speech in and out, and interrupting her (steps 2–3);
  - a real hosted agent (Cody, Hermes, Aggie or Claude) and spoken agent names;
  - the opt-in native, hardware and real-model suites.

## Limits and next

- Persona: she still says things like "I don't experience days or feelings". Persona writing is
  the owner's, after V1.
- Moving onto a window keeps a lingering presentation state from an earlier pose (the
  projection showed "waving" after a walk).
- Every reply says "Model context was shortened". The 8,000-character observation budget is
  nearly full on the owner's desktop. Raising `dialogue.context_max_chars` now that context is
  12,288 tokens is worth measuring.
- The owner's acceptance run (V1.md) is what decides V1.

HOW_TO_USE.md: updated.
