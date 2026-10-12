# Web Chat: talk by holding the microphone, task and memory chips

Model name: **Opus 5.5**. Checkpoint **2026-10-07 16:00:00 +01:00**, Europe/London. Status:
**built, component-tested and checked natively in an isolated profile.** This finishes the W2
items left open by the
[13:00 changelog](2026-10-07T130000+0100_GUI-WEB-SETTINGS-CHAT_Opus-5.5.md), and moves V1 steps
3 (voice) and 5 (agents) forward in the new Chat.

## What changed (`clients/panels/chat/`)

1. **Voice from the Chat microphone:**
   - Click once to start the local voice worker (`POST /api/v1/voice/local` `start`). The
     microphone stays closed.
   - Then hold to talk, with the mouse or Space: press sends `begin`, release sends `end`.
   - Losing the window or the press sends `stop`, which discards the recording. This is the same
     contract as the WinForms `PressToTalk`, as a tested `PressToTalk` class.
   - A dot shows Core's voice state: amber while loading, green when ready, red when listening,
     and red for an error.
   - Right-click opens the older Voice window.
2. **Task chips:**
   - The Chat follows Core's event feed (`/api/v1/events`, paged from its last sequence) and
     fetches each changed task's record.
   - A task appears under SORA's reply to the owner message that created it
     (`creator_message_id`), for example "Asked Cody · Working".
   - It uses her names for agents and Core's own status values. Click it to open Activity.
3. **Memory chips:**
   - Core's `memory.retrieved` events carry the dialogue request ID. The Chat remembers which
     reply answered each request it sent (kept in this browser profile, last 200), and shows
     "Used N memories" under that reply.
   - Opening the chip loads each memory's text, with a link to Memory.
   - Spoken turns are not linked, because their request ID is the voice generation's.
4. Expanded chips scroll into view.

## Verification

| Kind | What | Result |
|---|---|---|
| Component (JS) | Panel tests: event reading, task chip labels, reply linking, voice badge, hold-to-talk ordering (release during `begin`, discard, failed `begin`) | 26 passed |
| Component (C#) | `csharp_tests` | 401 passed |
| Fixture (full) | `scripts/verify.ps1` | 1019 passed, 25 skipped, 4 xfailed; mypy clean on 310 files; PWA 8/8; panels 26/26 |
| Native, isolated (`.local/gui-qa-20261007`, own Core and E2B) | Typed through the real composer via the debugging port: "remember my favourite colour is teal", then "what is my favourite colour?" | Reply "Your favourite colour is teal." carried **Used 1 memory**; opening it showed the remembered text |
| Native, isolated | Clicked the mic, held Space, then lost the window | Worker became ready with the microphone closed. While held: `microphone_open=true` and the badge was live. After losing the window: microphone closed, state ready, no message created. The audio worker was then closed |

## Not verified

- **Task chips:** not seen with a real agent task, because no hosted agent was started. Only the
  fixtures are tested.
- **Voice:** no real spoken turn through the Chat microphone. The press was discarded on purpose
  so nothing was recorded.
- **Not in the new Chat yet:** voice-turn memory chips, and the ability to select an exact task in
  Activity (the chip opens Activity at its default view).

HOW_TO_USE.md: updated (Voice in Talking to her, the Chat chips, removed the "not yet" line).
