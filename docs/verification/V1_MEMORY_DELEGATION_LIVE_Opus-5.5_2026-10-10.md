# V1 steps 6 and 9 (delegation and memory), live on E4B: findings and fixes

Observed by **Opus 5.5**, 2026-10-10, on the owner's PC.

**Evidence kind:** live model (Gemma 4 E4B, the owner's model and settings, copied), through an
isolated Core's real API (`.local/v1-memory-qa-r*-2026-10-10/`, port 8791). Not observed:
- the GUI, voice or avatar;
- the owner's profile, which was not touched;
- **the owner's own acceptance run**, which these results do not replace.

The owner reported that everything else in the V1 acceptance test, Quit included, works.

## Memory (step 9)

| Run | What happened | Fix |
|---|---|---|
| r1 | `remember` used for 2 of 4 facts, each called three times in a row. Missed "keep answers short" and "passport in the grey folder", **but claimed** "I have noted… logged this information" | `remember` offered once per turn; firmer tool guidance; the reply is told whether anything is being kept, and not to claim otherwise |
| r2 | 4 of 4 facts kept, but each also re-filed as "her own thought" ("The user stated…") | One memory tool per turn |
| r3 | 4 of 4 kept, no duplicates, no chatter. After a **full restart**, colour, birthday and passport were all answered correctly. Still said it would "set a reminder" | Abilities line: "no reminders, timers or alarms yet" |
| r4 | The "keep answers short" memory wasn't marked standing (E4B left the optional flag unset) | Core also recognises standing instructions from the owner's own words |
| r5 | 12 facts in a row: only 5 kept by the tool, 2 filed as her "thoughts", **5 missed (including a peanut allergy)** | **Safety net:** when no memory tool was called, a focused `RememberChoice` call after the reply; facts about the owner are no longer kept as her thoughts |
| r6 | 12 of 12 facts kept (5 by the tool, 7 by the safety net), no chatter, standing recognised. A thought that echoed his words was dropped | Thoughts echoing his words are dropped |
| r6 | "Tell me about the solar system": 166 words, then **39** once standing instructions were repeated at the end of her context | Standing instructions go last |
| r6 | "What am I allergic to?" missed the 3rd of 13 memories (only the 10 most recent were shown) | Recall by meaning **on by default**; shared-words recall when it is unavailable; the manager starts on every served Core |
| r6, after restart | All correct: "You are allergic to peanuts"; "Is there anything I should avoid eating?" → "You should avoid peanuts, as you are allergic to them" (meaning only, no shared words); cat Miso; friend Priya; level 3 parking. 13/13 memories embedded at start | |

## Delegation (step 6)

| Run | What happened | Fix |
|---|---|---|
| 1 | "Ask Claude how many Python files…": `delegate` chosen, then refused with "Unknown or stale project reference". No agent has a project folder in the owner's settings, so E4B invented `p1` | With no project folder configured anywhere, an invented reference means "no project" (with projects configured it is still refused) |
| 2 | With a project folder set (a copy of `src/sora/memory`): delegated to Claude, she kept chatting ("Your favorite color is teal"), and she reported "There are 12 Python files" in her own words (correct) | |
| 3 | "Cancel that task" about 4 s after delegating: the task stayed `cancel_requested` and Claude kept running. The cancel came while the agent was still starting: the adapter had no process yet, and the worker then waited for the result without cancelling | The worker cancels the agent when a cancel arrived during start. Regression test fails without the fix (the run hangs) |
| 4 | Same: the task ended `cancelled`, no Claude process was left, and she reported "that task was cancelled before it could be completed" | |

**Not run:**
- step 7 (no custom agent is enabled and LM Studio wasn't running);
- a spoken agent name;
- Cody, Aggie and Hermes.

## Component evidence

- pytest 1138 passed, 26 skipped, 4 xfailed; ruff and strict mypy clean; contracts fresh.
- New tests:
  - the safety net; standing instructions (stored, shown, last in context);
  - echo and owner-fact thoughts dropped; once-per-turn memory tools;
  - cancel during start (shown to fail without the fix);
  - invented project references with and without projects configured.
