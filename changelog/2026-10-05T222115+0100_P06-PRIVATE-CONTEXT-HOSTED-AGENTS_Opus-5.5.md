# Hosted agents may receive private context (owner decision)

Model name: **Opus 5.5**. Checkpoint **2026-10-05 22:21:15 +01:00**, Europe/London. Status:
**implemented, component-tested only**. Moves [V1.md](../V1.md) step 6 forward.

## Owner decision

In this session the owner said that hosted agents may receive private context and should not be
limited on file writes, because cloud agents can handle themselves reliably. The owner also
asked for delegation choices that cover all available agents, each with a default usage
description the owner can overwrite, including a general one for custom endpoints.

## Changes (commit `d32e81d`)

- `src/sora/routing/router.py`: local-only or private scope no longer excludes hosted agents,
  and no longer rejects an explicit hosted agent. It is recorded as `private_context` in the
  decision metadata. Antigravity and Claude are now classified as hosted, alongside Codex (a
  label only). Custom endpoints (`custom-*`) are never chosen by the automatic rules.
- `tests/verification/test_gemini_p03a_p06_audit.py`: the two strict expected failures that
  pinned the old P06.2/P06.3 criterion were replaced by tests of the new rule. Strict expected
  failures fall from 6 to 4. The P03A and P06.5 gaps are unchanged.
- `tests/routing/test_routing.py` and `tests/providers/test_claude_code.py`: the old
  privacy-containment tests were replaced by tests that private context reaches hosted agents.

## Verification (component)

`pytest tests/routing tests/verification tests/providers/test_claude_code.py`: 60 passed / 4
strict expected failures. The full suite was not rerun after this commit. The previous full run,
before it, was 929 passed with 8 Linux-only Windows-path failures.

## Not done: refused by this session's automated safety check

The rest of the owner's request was refused by the session's auto-mode safety check (reason
"Create Unsafe Agents"), even though the owner had approved it. The work was stopped and nothing
partial was committed:

1. **Unrestricted file writes for hosted agents.** The plan was to let Claude and Antigravity work
   directly in an owner-selected project folder, under Core's existing writer lease and
   before/after diff evidence, with permission-bypass defaults (`--permission-mode
   bypassPermissions` for Claude, `--dangerously-skip-permissions` for Antigravity). Today only
   Codex can work in a project folder, and Claude runs with no permission flags.
2. **Settings v10 and the delegation catalogue.** The plan was to add Claude and four
   custom-agent slots (nickname, spoken aliases, port, default model, usage description) with
   default usage descriptions the owner can overwrite, to show every registered agent with its
   name and description to SORA's delegate choice, and to add an OpenAI-compatible custom-endpoint
   adapter. A draft was reverted unfinished.

The owner can make these changes directly, or allow them for Claude Code (for example with a
permission rule in the session's settings), and ask again.
