# Changelog — 2026-09-29 — Agent-run fixes found by live testing

**Author:** Deepseek V4.1 Flash (Hermes)
**Scope:** fix the outstanding errors reported after the live memory/offload test of 2026-09-29.
**Not committed.** Working tree only, per instruction.

## 1. What this change set is answering

After the live test of memory + agent offload, five findings were reported. The owner ruled:

- the CLI's own model cache is **not** authoritative for the ChatGPT plan — the free plan carries
  **5.6 luna / terra / 6 luna**, and a Plus plan adds **5.6 sol / 6 sol / 6 astra**. Nothing needs
  "fixing" about the model roster; `--codex-model gpt-5.6-luna` was used because testing is
  restricted to **luna (5.6 or 6)**;
- "if there are any outstanding errors currently, look to fix them and come back with a changelog."

Findings 1–4 were errors; finding 5 is unfinished design work (see §4). One further error was
found *while verifying* the fixes (§3.5).

## 2. Fixes

### 2.1 Antigravity carried no changelog instruction and could not report a path (finding 1)

Every Antigravity run was reported `changelog_missing` because its adapter neither told the agent
to write an entry nor parsed a returned one.

- `src/sora/providers/antigravity.py` — the print-mode prompt now ends with
  `CHANGELOG_INSTRUCTION` (`src/sora/contracts/changelog.py`), and the requested JSON block now
  lists `changelog_path` / `changelog_entry` alongside `conclusion` / `facts` / `memory_updates`.
- `parse_antigravity_result` now reads `changelog_path` and `changelog_entry` from that block
  (`optional_text`) and copies them onto `NormalizedResult`, matching the Hermes and Codex
  adapters.
- Nothing else was needed: the service already verifies a claimed path and stores a returned
  entry verbatim when the agent could not create the file.

### 2.2 An empty `conversation_id` poisoned the session table (finding 2)

A failed Antigravity run returns `"conversation_id": ""`. The adapter stored the empty string, it
passed the `is None` guard in `_attach_native_session`, and `AgentSessionRecord(native_session_id="")`
then raised `ValidationError` — hiding the CLI's real message behind
`Runtime failure: ValidationError`.

- `src/sora/providers/antigravity.py` — a conversation id is only recorded when it is a non-blank
  string.
- `src/sora/runtime/service.py` — `_attach_native_session` treats a blank id as "no session"
  (defence in depth for every adapter, not just this one).

### 2.3 `--effort` conflicted with tiered model names (finding 3)

`agy` rejects `--model gpt-oss-120b-medium --effort low` with
`invalid model selection (...)`: a model whose *name* encodes its tier cannot take `--effort`.

- `src/sora/providers/antigravity.py` — when the configured model ends in `-low|-medium|-high|-max`,
  `--model` is passed and `--effort` is omitted (the name wins); otherwise `--effort` is passed as
  before. The earlier workaround of hand-matching `--antigravity-model` and `--antigravity-effort`
  on the command line is no longer required — a mismatched pair now launches cleanly.

### 2.4 Failures swallowed their reason (finding 4)

- `src/sora/runtime/service.py` — the generic failure path now appends the exception's own message
  (single line, bounded to 400 chars): `Runtime failure: <Type> - <detail>` instead of a bare
  `Runtime failure: <Type>`.
- `src/sora/providers/antigravity.py` — a wrapper payload with `status == "ERROR"` now raises
  `ProviderLaunchError` carrying the CLI's `error` text, which the (existing) ProviderLaunchError
  branch already surfaces verbatim.

### 2.5 Memory rationale was being lost to a too-small token budget (found while re-reading)

The live captures showed `rationale: null` with a truncated `reasoning` field: the memory rationale
call enables thinking and had `max_tokens=256`, so the thinking consumed the budget before any
answer was produced.

- `src/sora/providers/dialogue.py` — the explain call now asks for **768** tokens. Thinking stays
  attached to the capture as evidence only.

## 3. What was looked at (evidence)

- `agy --help` (flag semantics: `--add-dir`, `--effort`, `--conversation`, `--continue`,
  `--dangerously-skip-permissions`).
- `~/.gemini/antigravity-cli/conversations/<id>.db` — the CLI's own trajectory store. Its `steps`
  table holds the permission decision that explains §3.5:
  `permission check failed for write_file "...\<workspace>\sora-delegation-check.txt":
  user denied permission for write_file(...)`.
- The adapter's launch path (`providers/antigravity.py`), the service's session attach
  (`_attach_native_session`), the failure paths in `_handle_result`, and the memory explain call.

### 3.5 A resumed conversation keeps a recorded permission denial

Found while verifying §2.1: the run completed but reported
*"write permission to the repository was denied"*. Three CLI probes isolated it:

| Probe | Conversation | `--add-dir` | Result |
| --- | --- | --- | --- |
| 1 | fresh | no | write succeeded (`probe_write_1.txt`) |
| 2 | resumed `b2992af0…` | no | **denied**, 4 turns of retries |
| 4 | resumed `b2992af0…` | yes | write succeeded (`probe_write_4.txt`) |

The denial comes from a headless run made *before* `--dangerously-skip-permissions` was pinned —
the CLI recorded it against that conversation and replays it on resume.

- `src/sora/providers/antigravity.py` — the adapter now always passes
  `--add-dir <its working directory>`. The grant is unconditional: it is what lets a resumed
  conversation write, and it is exactly the "agent writes inside its granted root" model this
  project wants (no isolated sandbox).

## 4. Deliberately not changed

- **Coding writes remain Codex-only.** A coding-write task with `explicit_provider: antigravity`
  still fails with `Coding writes require the managed Codex worktree adapter.` That is the design
  as it stands (routing keys off worktree isolation; the write-authority rework is the open half
  of MEM3 — see the plan's §5.5). It fails loudly and now, per §2.4, with a readable reason.
- **`gpt-6-sol` default in the Codex config.** The observation that the CLI's `models_cache.json`
  lacks it was a false alarm: the cache is not authoritative for the owner's plan. No change.
- **Compaction.** Memory SQL compaction remains untested and untouched, per instruction.

## 5. Verification

- Unit/contract: `pytest -q` → **466 passed, 13 skipped**; `ruff check src/sora tests` → clean;
  `mypy src` → **Success: no issues found in 116 source files**.
  New tests: changelog fields parsed from an Antigravity JSON block; tiered model drops `--effort`;
  `--add-dir` carries the working directory; an ERROR payload raises with the CLI's message and
  records no session id; a blank native session id is not recorded; the runtime failure carries the
  exception message; the memory explain call asks for 768 tokens.
- Live, error path (§2.2 + §2.4) — real `agy`, invalid model:
  `ProviderLaunchError raised, message: Antigravity CLI error: invalid model selection
  (--model "not-a-real-model" --effort "low"): --effort is not supported for model
  "not-a-real-model"` and `session id recorded: None`.
- Live, full path (§2.1 + §3.5) — task `task-1a7d1f80-48f3-4ec2-8e79-f765d81e4c73` through the
  running Core (resumed conversation `b2992af0…`): the agent **wrote its own entry**
  `changelog/2026-09-29T113324Z_gitworktree_expl_SORA.md`, trace `changelog.verified`
  (`bytes: 387`, `sha256: b86091872b6c1fd177e2b7fccd059dc9e28fa92d4bd983ced089f271f77ece32`).
  Re-hashed by hand after the run — **exact match**. Task update token:
  `changelog:changelog/2026-09-29T113324Z_gitworktree_expl_SORA.md`.
- Earlier in the same sitting, and still the honest fallback: task
  `task-94d8d96f-…` (resumed, before the `--add-dir` fix) could not create files, returned the
  entry text, and Core stored it verbatim under
  `.local/manual-test/changelog/agents/…_ANTIGRAVITY.md` with
  `provenance: agent-authored, returned in the result contract` — no entry invented by Core.

## 6. Residual risks / notes

- The CLI's exact `--effort` support matrix is not documented. The rule here is the conservative
  one (tier-suffixed names never take `--effort`); if a model that does *not* encode a tier also
  rejects it, the run now fails with the CLI's own message instead of a bare type name.
- The `--add-dir` grant is what makes a *poisoned* conversation writable again; conversations that
  recorded a denial are otherwise still resumed happily. Retiring a session deliberately has no
  surface yet.
- Test artefacts left in `.local/manual-test/workspace/`: `probe_write_1.txt`, `probe_write_4.txt`
  (probe evidence), plus the agent's `changelog/` entry.
- The Core is running on the fixed build with
  `--codex-model gpt-5.6-luna --antigravity-model gpt-oss-120b-medium --antigravity-effort low
  --antigravity-arg=--dangerously-skip-permissions`. The normal launcher script does not know these
  pins, so a script restart reverts to the config defaults.
- Still uncommitted: git head `89f005f`, nothing staged.
