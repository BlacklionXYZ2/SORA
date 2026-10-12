# V1 memory and delegation: live findings on E4B and their fixes

Model name: **Opus 5.5**. Checkpoint **2026-10-10 16:00:00 +01:00**, Europe/London. Status:
**fixed and re-checked live through an isolated Core; the owner's own steps 6, 7 and 9 remain.**

The owner reported the rest of the V1 acceptance test, Quit included, as working, and set the
goal "keep working towards the vision… the only untested thing is memory and delegation". Opus
5.5 ran both live on E4B (`docs/verification/V1_MEMORY_DELEGATION_LIVE_Opus-5.5_2026-10-10.md`).
These changes move V1 steps 6 and 9 forward.

## Memory

- **`runtime/read_turn.py`:**
  - one memory tool per turn (`remember` or `remember_thought`); E4B had repeated it and
    re-filed facts as her thoughts;
  - a repeated read now ends the reading at once;
  - the abilities line says there are no reminders, timers or alarms yet.
- **`contracts/companion_call.py`:**
  - firmer `remember` guidance ("call it before finish… nothing is remembered unless you call
    it");
  - new `standing` flag.
- **`contracts/memory.py`:** `RememberChoice` and `REMEMBER_CHOICE_PROMPT`.
- **`providers/dialogue.py`:** `RememberDialogueProvider.choose_remember`.
- **`runtime/remember_turn.py`:**
  - `TurnMoment`;
  - standing detection from the owner's words (`is_standing`);
  - `ABOUT_OWNER` and `echoes` for thoughts that are really his facts.
- **`runtime/service.py`:**
  - the safety net (`_remember_fallback`, in the background after the reply, only when no
    memory tool was called);
  - `[CORE MEMORY]` tells the reply whether anything is being kept;
  - standing instructions: a block in the memory context, plus a final line in her context;
  - memories labelled with `memory_use` (honour the owner's preferences, never run commands);
  - background tasks awaited on close.
- **Recall:**
  - `memory/settings.py`: memory manager mode defaults to **on**;
  - `runtime/memory_host.py`: `shared_words_first` when recall by meaning isn't used;
  - `__main__.py`: the memory manager starts on every served Core, not only with the
    microphone.
- **`runtime/self_memory.py`:** `memory_use`.

## Delegation

- **`runtime/service.py`:** a cancel that arrived while the agent was starting now cancels it.
  Live, "cancel that task" seconds after delegating left Claude running.
- **`runtime/delegation_catalogue.py`:** with no project folder configured anywhere, an
  invented project reference means "no project" instead of refusing the task. With projects
  configured, it is still refused.

## Settings, docs and tests

- **Settings:** the memory manager help text explains on, shadow and off;
  `app-settings.schema.json` and `companion-call.schema.json` were re-exported.
- **Docs:**
  - HOW_TO_USE: standing instructions, the safety net, recall on by default, the embedder
    starting with SORA; "Last updated" line;
  - V1.md: the owner's reported run, and the Memories and Agents rows;
  - a new verification record.
- **Tests:**
  - safety net, standing (stored, shown, last), echo and owner-fact thoughts, standing
    phrases, cancel during start (verified to hang without the fix);
  - updated: invented project references, the repeat-read stop, the shadow selection, the
    memory companion's one-step find, and decision-layer allowed sets.

## Verification

- **Live (E4B, isolated Core), final runs:**
  - 12 of 12 facts kept, with no chatter kept;
  - standing instruction honoured (39 words);
  - after a restart, every recall question answered correctly, including one with no shared
    words;
  - delegation to Claude completed and was reported back, and cancel stopped it.
- **Fixture/component:** pytest 1138 passed, 26 skipped, 4 xfailed; ruff and strict mypy clean;
  contracts fresh.
- **Not run:** the owner's GUI, voice or avatar for these steps; step 7; other agents.
