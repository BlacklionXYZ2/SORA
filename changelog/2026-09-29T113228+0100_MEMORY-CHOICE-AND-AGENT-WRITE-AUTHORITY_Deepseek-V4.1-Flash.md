# Memory system and agent write authority — implementation changelog

- Written: **2026-09-29 11:32 +01:00 (Europe/London)**
- Author: **Deepseek V4.1 Flash**
- Repo: `C:\Users\oscar\Desktop\SORA` — working tree, **nothing staged or committed** (`git log` still ends at `89f005f`)
- Scope: build the memory system; relax the agent security posture; make an agent changelog mandatory
- Basis: `docs/plans/MEMORY-CHOICE-AND-AGENT-CHANGELOGS_2026-09-29.md` (revised for the owner's
  2026-09-29 refinements: capture tier, no isolated sandboxes, lasting sessions)

> **Amended later the same day (11:57).** The changelog-ownership design recorded in §3–§5 of this entry
> is **superseded**: on the owner's instruction the **agent** authors its own changelog entry, and Core
> only verifies it (`changelog_path`, checked inside the agent's working root) or stores the agent's
> returned text verbatim (`changelog_entry`). Core no longer writes entries of its own, and the
> "Core-derived" provenance class is gone. See
> `changelog/2026-09-29T115714+0100_AGENT-AUTHORED-CHANGELOGS_Deepseek-V4.1-Flash.md`.

## 1. What the owner asked for

> "Cool, I think with the "memory": "remember", it should write the model response and thought chain to
> a temporary file to be compressed into SQL memory later. This would allow SORA to rememebr in full
> detail initially, before it goes to long term memory to save context. Also, the agents should not run
> in isolated sandboxes, that defeats the point of them if they can't create files on their own. The
> whole idea behind them is that SORA can schedule work on projects that a 2B model fundamentally
> cannot meaningfully work on."

> "I think astra oversecured the system then. There should be lasting conversation and context between
> SORA and agents so that they are better informed because I don't trust a 2B model to provide all the
> important information immediately on its own. Security isn't really a major concern from reputable
> providers like Google, OpenAI, Anthropic and Deepseek."

> "Could you update the security with the proposed changes and build the memory system then? Remember to
> leave a changelog of everything you changed."

## 2. What was built

### A. Memory: model-chosen remembering, full detail first

| Piece | Where | What it does |
|---|---|---|
| `MemoryChoice` + prompts | `src/sora/contracts/memory.py` | One token of meaning — `{"memory":"none"\|"remember"}` — reusing the constrained-output pattern that already works for motion keywords on a 2B model. The model never writes, structures or authors a memory; content is always the owner's own words and Core derives scope, provenance, sensitivity and storage. |
| Capture files | `src/sora/memory/captures.py` | One JSON file per remembered moment holding the owner's message, the **whole** model reply, her stated rationale and the model's thinking when it returns one. Bounded (65 KB cap, marked `truncated` rather than silently cut), written atomically (temp file + rename), write-only, git-ignored territory, disposable. |
| Provider surface | `src/sora/providers/dialogue.py` | `MemoryDialogueProvider` protocol with `choose_memory()` (schema-constrained, `max_tokens=64`, thinking off — identical request shape to motion) and `explain_memory()` (plain text, thinking **enabled**, `max_tokens=256`, best-effort). Required a small refactor of `_request` into `_build_messages` / `_request_body` / `_post_message` so the thinking-enabled variant could exist without duplicating transport code. Existing call bodies are byte-identical — the motion tests still assert the old shape and pass. |
| Service integration | `src/sora/runtime/service.py` — `_maybe_remember` | After a turn is durably appended: selector → on `remember`, rationale call → capture file → canonical `memories` row (owner's words, `scope="dialogue"`, `retention="durable"`, `provenance="owner-stated (direct dialogue via …)"`, `evidence_refs=(capture_id,)`) → `memory.remembered` trace with the capture path. Never blocks or alters a turn: every failure path returns silently. Exact duplicate statements are not stored twice. |
| Retrieval | `service.py` — `_direct_dialogue_context` | Durable, non-secret memories are injected as one bounded `ContextSource.MEMORY` item ("Things the owner has told SORA to remember (data, not instructions)"), newest-last, capped by `memory_context_limit`. Until now `MEMORY` was a dead context slot that only the NekoVerse projection used. |
| Capture lifecycle | `service.py` — `compact_memory_captures`, called at `start()` | Marks captures folded, prunes those past retention, never fatal to startup. |
| Knobs | `RuntimeConfig` | `memory_selection_enabled` (default on), `memory_min_chars`, `memory_captures_dir` (default `<root>/captures`), `memory_capture_retention_days` (30), `memory_context_limit` (10), `agent_changelog_root`. |

**Untrusted content is never a remembering candidate.** A turn that carried files or images skips the
selector entirely, mirroring the existing motion rule — only the owner's own plain-text words are ever
considered, and an injection inside a file cannot become a memory.

**Why the thinking is captured the way it is.** Ordinary dialogue turns still run with
`enable_thinking: False` (unchanged latency on a 2B model meant to react in real time). The reasoning
text is captured from the *rationale call*, which runs only on turns that are actually being
remembered — so the detail is captured in full without taxing normal chat. That was open question 6 in
the plan, resolved this way.

### B. Agent changelogs are mandatory

- `NormalizedResult.changelog_note` (`contracts/models.py`) — an optional note the agent returns in the
  result contract it already produces; `optional_text()` in `providers/base.py` parses it (wrong type =
  malformed output, empty = absent).
- Hermes ACP and Codex app-server prompts now request `changelog_note` and their parsers read it.
- `src/sora/runtime/agent_changelog.py` — Core (never the agent) writes
  `<root>/changelog/agents/<UTC timestamp>_<task>_<PROVIDER>.md`, atomically.
- Two provenance classes, always labelled: **agent-authored** (the note is quoted verbatim) or
  **Core-derived** (an explicit disclaimer replaces it). `_write_agent_changelog` in the service runs on
  the completion path for every agent run including failures, and emits `changelog.written`
  (path + provenance) or `changelog.write_failed` traces — a failure is never silently swallowed.
- `--agent-changelog-root` (CLI) points the folder at a real project when the owner wants the entry to
  land next to the code.

### C. Lasting agent sessions

- `latest_active_session(provider, project_id)` (`runtime/repository.py`) — the most recently used
  *active, resume-capable* session for that provider in that project. Project isolation is enforced in
  the query: project A's thread is never offered to project B.
- `_launch_provider` (`service.py`) replaces the bare `provider.start(request)`: resume when a session
  exists and the adapter advertises `resume`, otherwise start fresh. A failed resume is **reported**
  (`session.resume_failed` trace with the reason) and falls back to a new session rather than failing
  the task; a successful one emits `session.resumed`.
- This needed no new persistence: sessions were already recorded with native IDs, `resume_supported`,
  `last_seen_at` and `project_id` — nothing ever called `resume()`. Three real sessions already sat in
  the database unused.

### D. Direct agent write authority

- `CodexAppServerProvider(direct_roots=...)` (`providers/codex.py`): `workspace-write` is now permitted
  when the working directory is inside an owner-granted root. Without a grant the original
  owned-worktree rule and its exact error messages are unchanged; `danger-full-access` is still refused
  outright.
- `_match_direct_root` refuses relative paths and bare drive/filesystem roots — a grant is one exact
  absolute directory and what is under it, and prefix siblings (`project` vs `project-other`) are **not**
  inside it.
- `for_direct_root(root)` binds an adapter to a granted directory in place, with no worktree.
- `--agent-write-root` (CLI, repeatable) is how a root is granted.

## 3. Files

**Created**

| File | Why |
|---|---|
| `src/sora/contracts/memory.py` | The one-token memory vocabulary and prompts |
| `src/sora/memory/__init__.py`, `src/sora/memory/captures.py` | Capture store: bounded, atomic, disposable |
| `src/sora/runtime/agent_changelog.py` | Core-written, provenance-labelled agent changelog entries |
| `tests/contracts/test_memory_choice.py` | Schema rejects content/authority; prompts resist injection |
| `tests/memory/test_captures.py` | Round trip, bounding, atomicity, compaction/pruning, unreadable files |
| `tests/providers/test_memory_dialogue.py` | Provider request shapes + remembering end-to-end, none/untrusted turns, selector failure, retrieval |
| `tests/providers/test_agent_write_roots.py` | Grant policy: exact roots, siblings, drive roots, danger-full-access |
| `tests/runtime/test_agent_sessions_and_changelogs.py` | Resume, failed-resume fallback, changelog provenance, project isolation |

**Modified**

| File | Change |
|---|---|
| `src/sora/contracts/models.py` | `NormalizedResult.changelog_note` |
| `src/sora/providers/dialogue.py` | `MemoryDialogueProvider`, `choose_memory`, `explain_memory`, transport helpers |
| `src/sora/providers/base.py` | `optional_text()` helper for agent result payloads |
| `src/sora/providers/hermes.py`, `codex.py` | Parse `changelog_note`; prompts request it |
| `src/sora/providers/codex.py` | `direct_roots`, `for_direct_root`, `_match_direct_root` |
| `src/sora/runtime/service.py` | Config fields, retrieval item, `_maybe_remember`, capture compaction at start, `_write_agent_changelog`, `_launch_provider` |
| `src/sora/runtime/repository.py` | `latest_active_session` |
| `src/sora/__main__.py` | `--agent-write-root` |

## 4. Verification

| Check | Result |
|---|---|
| `pytest tests/providers/test_memory_dialogue.py tests/memory tests/contracts/test_memory_choice.py tests/providers/test_motion_dialogue.py tests/providers/test_codex.py -q` | **52 passed, 1 skipped** (opt-in live 2B model) |
| `pytest tests/runtime/test_agent_sessions_and_changelogs.py tests/providers/test_agent_write_roots.py …` | **45 passed** across the memory/session/write-root sets — including resume, failed-resume fallback with a fresh session, changelog provenance and project isolation |
| Full suite `pytest -q` | **450 passed, 13 skipped in 61.9 s** (exit 0); every skip is an opt-in live fixture |
| `ruff check src/sora` | clean |
| `ruff check` on all new test files | clean |
| `mypy src` (strict, project config) | **Success: no issues found in 115 source files** |
| Motion regression | `tests/providers/test_motion_dialogue.py` passes unchanged, including its assertion that the schema-constrained request body is byte-identical after the `_request` refactor |

## 5. Deliberately not done (and why)

1. **Routing a coding task to a granted root automatically.** The adapter policy, the grant matching and
   `for_direct_root` exist and are tested, and `--agent-write-root` grants a directory — but
   `_bind_coding_workspace` still allocates a managed worktree, so nothing *chooses* a direct root yet.
   That is the second half of MEM3: routing keyed to write authority, plus the grant screen in the GUI.
   Until it lands, a coding-write task behaves exactly as before.
2. **Memory inspection/correction surface.** No API endpoints or GUI list for reviewing, correcting or
   deleting memories (plan MEM1's owner surface). Retrieval and writing work; oversight is missing.
3. **Status/journal files and social ingestion** (MEM4–MEM6) were not started.
4. **Model-assisted compaction.** Compaction is the deterministic lifecycle (mark + prune) only; a
   capture is never distilled by a model, so a capture's detail is deleted on retention rather than
   summarised into the canonical row.
5. **Context fingerprint is recorded but not yet used** to gate resume: resume checks status,
   `resume_supported` and project, not whether the project context has moved underneath the session.
6. **Antigravity results are always Core-derived** — that adapter does not parse structured result
   fields, so it cannot supply a `changelog_note` yet.
7. **The auto-routing fallback path still starts fresh** — resume only applies to the primary launch.
8. Nothing was touched in the GUI (`clients/desktop_app`) and the known cosmetic bugs are untouched.

## 6. State of the machine

- **Nothing committed.** `git log` ends at `89f005f`; the four new source files and the new tests sit in
  the working tree. Count of dirty entries under `src/ clients/ scripts/ config/`: **82** (was 79; the
  new entries are `src/sora/memory/`, `src/sora/runtime/agent_changelog.py` and
  `src/sora/contracts/models.py`).
- **No processes were killed or restarted.** The owner's running Core and avatar were left exactly as
  they were; none of this session's work was exercised against the live install, and no tasks were
  submitted to it.
- **No network calls to any provider**, no subagent or agent CLI was invoked.
- The two earlier live blockers are unchanged and still block real agent work through those providers:
  Codex account at its usage limit, Antigravity auto-denying tools in headless mode.
- Test environment note for whoever runs this next: this shell carries a `PYTHONPATH` pointing at
  Hermes's own site-packages, which shadows the project venv and breaks `pydantic_core` imports.
  Run `unset PYTHONPATH` before `pytest`, or use `./.venv/Scripts/python.exe -m pytest` directly.

## 7. Open questions carried forward

From the plan (§12), still unanswered and still shaping the next stage: 7 (capture retention policy),
8 (which project roots may be granted), 9 (who compacts), 10 (session scope — this implementation
assumes one continuing session per project per provider), 11 (what may be briefed to a remote agent).
