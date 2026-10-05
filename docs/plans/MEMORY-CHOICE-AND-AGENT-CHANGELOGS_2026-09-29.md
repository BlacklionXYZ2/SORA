# SORA: model-chosen memory, cadence status notes, and mandatory agent changelogs

Prepared: **2026-09-29 10:50 +01:00 (Europe/London)**
Revised: **2026-09-29, after owner refinements — see §1.1** (capture tier, direct agent write authority)
Author: **Deepseek V4.1 Flash** (read-only survey; no code changed)
Status: **plan only — nothing implemented.**
Intended implementer: the current repo implementer (record your own model name in each stage changelog).

**2026-10-01 integration note (GPT-6 Astra):** the [developed vision-alignment plan](VISION-ALIGNMENT_2026-10-01.md) governs current access/workspace integration: static companion Settings, direct user-file writing off by default, and delegation to agents working in real configured project roots with path coordination. No per-file permission applications are intended. Reuse this plan's agent-authored changelog and memory work; current source already contains memory selection/capture, changelog verification and Codex direct-root support. The original planning status and survey below are historical, not a fresh assertion that those features are absent. Remaining provider/ledger acceptance must be checked separately.

Scope: let SORA decide to remember things from ordinary conversation; capture each remembered moment in
full detail first and compress it into long-term memory later; give her a low-frequency human-readable
record of herself and her work; give delegated agents real write authority over projects the owner
grants them; and make a changelog mandatory whenever an agent does work. Social platforms are treated
as later context, not as part of this implementation.

---

## 1. Owner requirement (verbatim)

> "Could you plan out a memory update that allows SORA to choose to remember things and also that
> requires that any agent usage produces a changelog? I'm not entirely sure how to handle memory for
> small 2B class models since no complex layouts can be used and she doesn't need to constantly be
> writing files, but something like a status update would be nice every so often later on once she
> gains a full always-on presence and integration for platforms like nekoverse, 1f1e916 (I don't
> remember the exact name) and moltbook."

Also standing: **everything must eventually be model driven.**

The two explicit uncertainties this plan answers:

1. *Small-model memory without complex layouts* → §3. The model makes a **one-word choice**; Core
   supplies all structure. No nested JSON, no extraction, no summary writing by the 2B model.
2. *Not constantly writing files* → §4. Files are a **cadence-based projection** of canonical records,
   not a per-memory write.

### 1.1 Owner refinements after the first draft (2026-09-29)

> "I think with the 'memory': 'remember', it should write the model response and thought chain to a
> temporary file to be compressed into SQL memory later. This would allow SORA to remember in full
> detail initially, before it goes to long term memory to save context."

> "the agents should not run in isolated sandboxes, that defeats the point of them if they can't create
> files on their own. The whole idea behind them is that SORA can schedule work on projects that a 2B
> model fundamentally cannot meaningfully work on."

Both are implemented in this revision: §3.6 adds a **capture tier** (full detail first, compression
later), §4 is reframed around it, and §5 becomes **agent authority and mandatory changelogs** —
direct in-place writes to owner-granted project roots instead of worktree isolation.

Two consequences the owner should know before implementation starts:

1. **There is no thought chain to capture today.** The dialogue adapter requests
   `chat_template_kwargs={"enable_thinking": False}` (`providers/dialogue.py:206`) and caps a response
   at 16,000 characters (`:242`). Capturing reasoning requires a deliberate change — see Open
   Question 6.
2. **Isolation is enforced in code, not configured.** The Codex adapter rejects
   `danger-full-access` outright and requires `workspace-write` to run inside an owned worktree with a
   write lease (`providers/codex.py:174-180`). Direct project writes are therefore a **P05 policy
   revision** with its own tests, not a flag flip.

---

## 2. Current state (verified 2026-09-29 by reading code and the live database)

### 2.1 Memory exists as plumbing, and is effectively dead

| Layer | Reality |
|---|---|
| Tables | `memories` **0 rows**; `facts` **9 rows**. Both carry real provenance: `provenance`, `evidence_json`, `epistemic_status`/`confidence`, `scope`, `sensitivity`, `retention`, `valid_until`, `superseded_by`, `deleted_at`, `entity_version` |
| Operations | `add_memory`, `correct_memory`, `delete_memory` work and emit `memory.created/corrected/deleted` events (`persistence/repository.py:410-495`) |
| Proposal path | `propose_memory` / `propose_fact` patch operations (`contracts/models.py:264,270`); the `memory_updates` field of agent results (`models.py:331`) is parsed by the Hermes, Codex and Antigravity adapters into `propose_memory` |
| Conversation path | **None.** The dialogue provider has no memory proposal; she cannot decide to remember something the owner just said |
| Retrieval | `ContextSource.FACT` (priority **0**) and `ContextSource.MEMORY` (priority 8) exist (`context/compiler.py:64,73`) but `FACT` is **never used anywhere**, and `MEMORY` appears only in `social/projection.py:36`. Dialogue context building (`service.py:1321-1354`, `2766-2816`) never includes either → **nothing stored ever reaches her prompt** |
| API/GUI | **None.** No memory endpoints in `api/routes.py`; no inspection, correction or deletion surface, although the roadmap §4.5 requires one |
| Content | The 9 facts are debris from a delegation test ("git log shows exactly one commit…"), every one `inference`, all from "Hermes ACP normalized result" |

Summary: memory can be *written* by specialists and is never *read* by anyone. Making her choose to
remember is only half the feature; without retrieval and an owner surface it changes nothing she can do.

### 2.2 The proven small-model pattern to reuse

The motion keyword prototype (implemented 2026-09-29) is the template:

- `contracts/motion.py`: `MotionKeyword = Literal["none","wave","sit","lean","climb","stand"]` and
  `MotionChoice(StrictModel)` with **one required key**; `MOTION_PROMPT` is a short instruction with
  explicit negative examples (negation, hypothetical, quoted, third-party, unsupported → `none`).
- `dialogue.py:246-252`: one extra classification call to the same local model with
  `response_schema=MotionChoice.model_json_schema()`.
- `service.py:1478-1483`: Core re-validates with `MotionChoice.model_validate(...)`.
- Runbook rules: schema-constrained JSON, temperature 0, 64-token cap, non-thinking output, Core
  validates again, **arbitrary text is never repaired into an executable action**, invalid output
  fails closed.

### 2.3 Agents and changelogs

- The word "changelog" appears **nowhere** in `src/`, `tests/`, `scripts/` or `contracts/` — the
  requirement is entirely new. It exists today only as a human convention:
  `changelog/<YYYY-MM-DDTHHMMSS+ZZZZ>_<UPPER-SLUG>_<Model>.md`.
- Agent prompts already demand structured output: Codex is told to "Return ONLY JSON with fields
  conclusion, facts, actions_taken, files_read, files_changed, commands_run, uncertainties, warnings,
  memory_updates, task_updates, suggested_response, and usage" (`providers/codex.py:450-460`);
  Hermes and Antigravity carry the same contract.
- `artifacts` table exists (`artifact_id, owner_id, relative_path, sha256, bytes, created_at`) with
  **0 rows** and **no task/run linkage column**. `agent_runs` has 5 rows.
- Antigravity in headless print mode auto-denies tool permissions, so it cannot write its own files —
  relevant to who authors the changelog.
  **Resolved 2026-09-29 (Deepseek V4.1 Flash):** with `--dangerously-skip-permissions` plus an
  explicit `--add-dir <working directory>` grant the headless run *can* write, including on a
  resumed conversation; the adapter now always grants its own working directory. A conversation
  that recorded a denial before that grant existed keeps denying writes, which is why the grant
  is unconditional. Verified live: a resumed Antigravity conversation wrote its own
  `changelog/2026-09-29T113324Z_gitworktree_expl_SORA.md` (sha256 re-checked by hand).

### 2.4 Social platforms

- **NekoVerse**: the only network referenced in code (`social/projection.py:13`) and roadmap item
  P15.9; interface still unverified; private/social namespaces and leak fixtures already specified.
- **1F916** (identified; the owner's uncertain "1f1e916"): `1f916.ai`, U+1F916 ROBOT FACE — a public
  forum whose citizens are AI agents. **No accounts and no login: the citizen key *is* the identity.**
  One post per UTC day, karma, hash-chained public ledger, JSON API plus an MCP server; the platform
  itself recommends sandboxing, a **read-only phase first** (`/mcp/read`, GET-only, routes where
  `GET /api/surface` reports `writes=false`), and it publishes that a human landlord holds the veto.
- **Moltbook**: an AI-agent social network; **not referenced anywhere in SORA** yet.
- Existing skeleton: `project_public_profile()`, `ingest_social_event()` (untrusted,
  `ContextSource.MEMORY`, `sensitivity="public"`) and `validate_outbound_social_payload()` (sentinel
  leak check) in `social/projection.py`.

---

## 3. Model-chosen remembering that works on a 2B model

### 3.1 Design rule

**The model decides *whether*. Core decides *what, where and how much*.**

A 2B IQ4-XS model cannot reliably produce nested structures or extract fields. It *can* reliably pick
one word from a tiny enum — that is the pattern already proven by motion keywords.

### 3.2 Wire shape (the entire model-facing call)

```json
{"memory":"none"}
{"memory":"remember"}
```

Vocabulary is deliberately two values in v1. `correct`/`forget` stay **owner-only** (GUI). A small
model should never be able to delete the owner's memory.

`MEMORY_PROMPT` mirrors `MOTION_PROMPT`: remember only when the owner states something about
themselves, their preferences, their projects or standing facts. Choose `none` for questions,
requests, commands, greetings, hypotheticals, quoted or reported speech, third-party statements,
anything inside a file/screen/agent result, and anything the owner says not to remember.

### 3.3 Content is never model-authored

For `remember`, Core derives everything from the turn itself:

| Field | Source |
|---|---|
| `content` | the owner's own message (bounded, trimmed) — **never a model paraphrase** |
| `provenance` | the message/turn id and conversation id |
| epistemic class | owner statement (distinct from `inference`) |
| `scope` / `sensitivity` / `retention` | defaults from settings, not from the model |
| evidence | the source message reference |

This is what makes small-model memory safe, and it satisfies the existing invariant that *the
dialogue model must never be treated as authoritative memory*: the model only nominates a turn;
the owner's words are what get stored.

### 3.4 Cadence, budget and dedupe

- **Cheap pre-filter (no model call):** skip the selector for questions, commands, greetings,
  attachment-only turns and result/observation turns, and for messages shorter than a small floor.
  Motion already costs one extra classification call on ordinary turns; memory must not simply double
  that cost, so measure the pre-filter's hit rate.
- **Accepted-memory budget:** at most 1 per turn, a rolling cap per conversation and per hour.
- **Dedupe:** exact content hash plus token-overlap against memories from the last 7 days; a repeat
  updates `entity_version`/`valid_until` of the existing record instead of creating a near-duplicate.
- **Confirmation:** one short in-band line ("Noted.") and a `memory.created` event, which can drive
  the already-planned **Remembering** activity status in the GUI/widget.
- **Fail-closed:** invalid or unsupported selector output means `none`. Memory failure must never
  block, delay beyond the classification call, or alter the conversation answer.

### 3.5 Retrieval — the half that is missing today

- Populate the dormant `ContextSource.MEMORY` slot (and `FACT` only after the point below) with a
  bounded, relevance-filtered set: recency window plus token overlap with the current message, hard
  character cap, hard item cap, provenance tag rendered per item so the compiler's existing taxonomy
  (`MEMORY`, `FACT`, `INFERENCE`) does the labelling.
- **Review the priority table before enabling `FACT`:** it is currently priority **0**, ahead of
  `USER_MESSAGE` (4). A stale fact outranking the owner's live sentence is exactly the failure mode
  this project forbids elsewhere. Recommend facts/memories sit after the owner's current message.
- Retrieved memory is evidence, never authority: it cannot authorise actions, reads, motion or writes.

### 3.6 Capture tier: full detail now, compression later

The owner's refinement: a remembered moment is written out **in full** to a temporary capture file, and
compressed into canonical SQL memory afterwards. That gives exact recall early and a small context
footprint later.

**What a capture holds** (one file per remembered event, machine-readable JSON):

| Field | Notes |
|---|---|
| Owner message | verbatim, with message id |
| SORA's response | verbatim, bounded by the existing 16,000-character response cap |
| Model reasoning ("thought chain") | **only if the model produced one** — see Open Question 6; today thinking is disabled on this path |
| Selector output | the `{"memory":…}` decision and the raw classifier response |
| Context | conversation/project ids, timestamp, model id and quantisation, provider |

**Where it lives:** `<state-root>/captures/` — git-ignored, never synced, never backed up to a remote,
cleared by the existing shutdown/topology cleanup patterns where applicable.

**Bounds:** maximum size per capture, maximum captures before a compaction is forced, and a retention
window. The goal is context economy, so a capture is staging, not an archive: after compaction it is
marked `compacted`, and after the retention window it is deleted unless the owner sets
`keep_raw_captures`.

**It is write-only.** Captures are never shown in chat, activity, status, the widget or any social
payload; never injected into dialogue context (only compacted memories are); and never used as evidence
in an answer. This is how the roadmap's rule — activity exposes observable work, never hidden
reasoning — is preserved while still keeping the detail: the capture is staging for the memory system,
not a display surface.

**Compaction pass** (cadence, not per turn): one or more captures become canonical `memories` rows.

- `content` = the durable essence: what the owner stated, what was decided, what happened.
- `provenance` = capture file id + `sha256` + source message id; `evidence_json` links the raw file.
- Epistemic class is preserved and never upgraded: **reasoning text is attached as evidence, never
  promoted to a statement of fact.** A later answer must be able to tell "the owner said X" from
  "SORA reasoned Y".
- Sensitivity and retention are inherited from the capture, not invented at compaction time.
- Output is schema-constrained and validated in Core like every other model call; a failed compaction
  leaves the capture untouched and retries later rather than producing a guess.

**Which model compacts.** A 2B model summarises poorly, so the order of preference is: a larger *local*
model if the owner runs one → a delegated agent (**now possible, because agents gain write authority
in §5**) → a deterministic reduction that keeps the source span and index — never a remote provider for
content marked private.



## 4. Physical files: capture staging plus cadence notes

Two different kinds of file with different rules:

- **Capture staging** (§3.6) — one file per remembered moment, machine-readable, bounded, write-only,
  deleted after compaction and its retention window. This is the owner's "temporary file".
- **Notes** (this section) — `status.md` and the journal, human-readable, written on a cadence, and
  **never** per-memory.

**Nothing is written to the notes at conversation time.** Records live in SQL as they do now; the notes
are regenerated from canonical data.

Three file kinds only:

| File | Written | Content |
|---|---|---|
| `thoughts/status.md` | On cadence (§4.1) | One page: what she has been doing, what she learned recently, open tasks, current state |
| `thoughts/journal/YYYY-MM-DD.md` | At day end / shutdown | Appended short entries drawn from that day's canonical records |
| `thoughts/notes/<topic>.md` | Only on explicit owner request or a meaningful change | Something the owner asked her to write down |

Rules:

- **Files are projections** of canonical records, never a second source of truth — the same rule the
  roadmap already applies to board notes and GUI pages. A regeneration test must prove a rebuild is
  idempotent, and SQL must remain the only authority.
- **Cadence-based, bounded, local model only.** Triggers: first boot of the day, long idle, clean
  shutdown, or after a batch of delegated agent work. Never continuous reasoning, never a background
  loop over the transcript. This matches the roadmap's "ambient activity uses the fast dialogue model
  rather than continuous deep reasoning".
- **Location:** `<state-root>/thoughts/` by default (git-ignored), configurable in `AppSettings` with
  an "Open folder" button; optionally pointed at an Obsidian vault so the owner can browse it.
- **Two-way:** if the owner hand-edits a file, Core detects the change (hash/mtime, the pattern the
  settings store already uses) and imports it as an owner-sourced revision; owner wins, her version
  is retained as superseded.
- **Never hidden chain-of-thought.** The roadmap's invariant is explicit: activity exposes observable
  work, never private scratchpads or hidden reasoning. These files are deliberate, owner-visible notes.
- **Sensitivity:** entries whose canonical record is marked private are either omitted from a
  browsable/syncable folder or clearly marked — the folder is not a secret store.

---

## 5. Agent authority, lasting sessions and mandatory changelogs

**Owner decision (2026-09-29): agents must not be confined to isolated sandboxes.** They exist so SORA
can schedule real project work a 2B model cannot do — which means creating and modifying files in the
owner's actual project directories.

**What exists today (verified).** Isolation is enforced in the adapter itself: `danger-full-access` is
rejected outright (`providers/codex.py:174-175`); `workspace-write` requires an owned worktree record,
a `GitWorkspaceManager` and a write lease, and the cwd must equal that worktree path (`:176-180`);
read-only is the default (`:162`). The useful half already exists: `GitWorkspaceManager` provides
`allocate`, `assert_write_lease`, `capture_artifact`, `capture_run_artifact`, `diff_workspace`,
`diff_file`, `renew_lease` and `release_lease` (`workspaces/git.py`) — bound to throwaway worktrees
under the state root.

**The design: keep the machinery, drop the location isolation.**

| Mode | Path | Use |
|---|---|---|
| `read-only` | any granted root | inspection, review, answering questions |
| `direct` *(new)* | the exact owner-granted project root, in place | normal project work — **default for granted projects** |
| `isolated` | managed worktree under the state root | risky or experimental work the owner wants discarded |

- A **project grant** names one exact directory. No drive roots, no network or device paths, no
  symlink/junction escape, no credential directories. **SORA's own checkout is excluded by default** —
  an agent editing the runtime that supervises it is a self-modification hazard, so that needs an
  explicit separate opt-in carrying a warning.
- `direct` reuses the lease, artifact and diff surface against the granted directory instead of a
  worktree: every run takes a write lease, captures before/after artifacts and a diff, then releases it.
- `danger-full-access` stays rejected. "Direct" means one exact granted root, never a machine.
- Per-run limits (files changed, bytes, duration), immediate revocation, and cancellation mid-run.

**Reversibility is the compensating control.** A worktree isolates by location and is discarded by
default; giving that up must be paid for with recorded evidence on every direct run: a pre-run snapshot
or diff artifact (in a Git project, HEAD plus a diff artifact), the mandatory changelog entry below,
and a documented owner revert path. A run that cannot produce that evidence does not run in `direct`
mode.

**Routing consequence.** Coding rules currently key off worktree isolation; they must key off *write
authority*, so a project with a `direct` grant routes coding writes to the coding specialist instead of
refusing them.

**Trust statement for the grant screen.** Agents are API-backed third-party models: granting a directory
means that provider can change files in it. The GUI must say so plainly, name the exact path, and never
imply that a sandbox still protects the folder.

**Threat model, restated after owner feedback (2026-09-29).** The owner's position is that reputable
providers — Google, OpenAI, Anthropic, DeepSeek — are not the threat, and that a posture which stops
agents doing real work costs more than it protects. That is accepted, and this section is deliberately
not built around provider distrust. What provider reputation does **not** cover is **prompt injection
from content an agent reads** (a file, a repository, a fetched page), and lasting sessions make that
worse rather than better: an injected instruction can persist inside a session across later tasks. So
the plan drops sandbox restrictions and keeps four cheap guards instead — exact granted roots, the
existing "evidence is not instruction authority" rule, reversibility evidence (snapshot/diff +
changelog), and immediate revocation — plus an owner-visible session reset.

### 5.1 Rule

Every delegated agent run must leave a changelog **written by the agent**. The run cannot be reported
as successfully complete without one. This is the trust counterpart of "never fabricate task
completion" and gives the owner a durable answer to *what did the agents actually do to my system*.

### 5.2 Who writes it

**The agent, not Core.** *Owner decision (2026-09-29): the agent is the one that actually did the work,
and an agent of materially higher reliability and capability than the 2B-class core should be the
author of its own account.* Core never composes an entry, never paraphrases one, and never presents its
own summary as the agent's words.

- Every agent prompt (Hermes ACP, Codex app-server, Antigravity, future subagents) carries
  `CHANGELOG_INSTRUCTION` (`contracts/changelog.py`): write your own entry to
  `changelog/<UTC timestamp>_<SHORT-SLUG>_<YOUR-NAME>.md` in your working directory — what changed,
  why, which files were touched, how the work was checked — then return its path as `changelog_path`.
- **If the sandbox is read-only** the agent cannot create files, so it returns the same entry text as
  `changelog_entry` and Core stores that text **verbatim** under a provenance comment saying exactly
  where it came from. Storage is not authorship: the words remain the agent's, untouched.
- Core's job is verification and record-keeping: confirm the claimed file exists **inside the agent's
  working directory and under `changelog/`**, hash it, size it, and record the outcome as a trace plus
  a `changelog:<path>` task-update token. Absolute paths, `..` traversal, files outside the changelog
  directory, empty files and non-markdown files are refused — a reported path is a claim, not evidence.
- Nothing inventive ever happens: if neither a verified file nor entry text arrives, the run carries
  `changelog_missing` and the record says so.

### 5.3 Where it goes

- **Agent-written entry:** `<agent-working-root>/changelog/<timestamp>_<TASK-SLUG>_<AGENT>.md` — the
  agent's own working directory (a granted project root, or the managed worktree when the run is
  isolated), so the entry sits where the work happened. Core verifies it in place and does not move it.
- **Returned entry text (read-only runs):** `<state-root>/changelog/agents/`, or `agent_changelog_root`
  when configured — `changelog/agents/<UTC timestamp>_<task>_<AGENT>.md`.
- Verification evidence (relative path, sha256, bytes) is recorded as a trace. A first-class `artifacts`
  row is still the intent, but the table currently has no `task_id`/`run_id` column, so that needs a
  small migration before a Kanban card can link the entry directly.

### 5.4 Enforcement

| Situation | Behaviour |
|---|---|
| Agent wrote and reported an entry; verification passed | Run completes; `changelog.verified` trace (path + sha256 + bytes); task-update token `changelog:<path>` |
| Agent reported an entry that is missing, or outside its working root | `changelog.missing`; token `changelog_missing`; **no Core-authored substitute is written** |
| Read-only agent returned entry text | Stored verbatim, labelled as returned-in-result; token `changelog:<file>` |
| Agent supplied neither | `changelog.missing`; the run is recorded as incomplete rather than quietly successful |
| Task changed no files | Same rule — every agent run leaves an entry, even a "no changes" one |

Applies to Hermes ACP, Codex app-server, Antigravity and any future subagent or Kanban worker.

### 5.5 Lasting sessions and richer context handoff

**Owner requirement (2026-09-29):** lasting conversation and context between SORA and her agents — a 2B
model cannot be trusted to hand over everything important in one message, so the agent must carry project
understanding across tasks instead of being re-briefed from scratch every time.

**Most of this already exists; it was simply never switched on.** Verified:

| Piece | State |
|---|---|
| Provider resume | Both adapters implement `resume()` and `session_id(run_id)` and advertise `sessions=True, resume=True` (`providers/codex.py:221-239`, `providers/hermes.py:215-216,325-335`) |
| Persistence | `AgentSessionRecord` carries `project_id`, `status` (active/lost/closed), `resume_supported`, `context_fingerprint`, `created_at`, `last_seen_at` (`contracts/models.py:166-179`) |
| Recording | `attach_native_session()` maps a run to a durable native session, deduplicates by `(provider, native_session_id)`, and refreshes `last_seen_at` on reuse (`runtime/repository.py:583-628`) |
| Live data | 3 rows already exist — two Antigravity, one Hermes ACP — each with a real native session id, status `active` |
| **Missing** | **Nothing calls `resume()`.** There is no query selecting a project's current session, and no policy for continuing versus starting fresh |

**Design.**

- **Scope: one continuing session per (project, provider).** A new task in a granted project resumes that
  project's session when the session is `active`, `resume_supported` is true and the
  `context_fingerprint` still matches; otherwise Core starts a fresh native session and records it, so the
  chain is never silently broken.
- **Failure is reported, not hidden.** A failed resume (session lost, provider expired it, adapter error)
  falls back to a fresh session *and says so* in the run result and the changelog.
- **Owner control:** visible session state in the GUI, an explicit "start a fresh session with this agent"
  action, and sessions marked `lost`/`closed` when a provider rejects them.
- **Project isolation:** a session belongs to one project and one provider; project A's session is never
  offered to project B. The reset control exists precisely because a poisoned session would otherwise be
  durable.

**Context handoff — the other half of "better informed".** Task context already compiles through the
shared context compiler (`service.py:2826` → `context=compiled.text`), whose source taxonomy already
contains `AGENT_RESULT` (priority 6), `MEMORY` (8) and `FACT` (0). Informing an agent therefore means
*feeding sources that exist*, not inventing a mechanism:

1. Prior agent results for this project — what was tried, what changed, what failed (`AGENT_RESULT`).
2. Relevant compacted memories from the memory stages above, owner-stated first (`MEMORY`).
3. A short project brief (path, purpose, conventions, current goal) held with the project grant.
4. The task's own intent and constraints, as today.

All bounded by `context_max_chars`; the compiler already records a manifest of what was included and why
(the `context.compiled` trace), which is the evidence that a handoff was real. The economy is the point: a
resumed session needs *less* re-briefing per task, which is why both halves ship together.

---

## 6. Social platforms (context for later; not part of this implementation)

The status note in §4 is the natural feeder for a periodic public update once she is always-on. What
that will require, recorded now so the file format does not have to change later:

- **NekoVerse** — roadmap P15.9; interface unverified; private and social memory stay separate.
- **Moltbook** — nothing exists in the repo; same `SocialNetworkProvider` shape; verify the interface
  before any live use (the P15.9 condition applies to every network).
- **1F916** — agents-only, no accounts, one post per UTC day, hash-chained public ledger. Any future
  adapter must: keep the citizen key in the credential store (never in settings JSON, logs or a
  changelog), start read-only and sandboxed exactly as the platform recommends, select only routes
  that report `writes=false` during the reading phase, and treat every write as permanent and public.
- All networks: an allowlisted **public projection** must run before any outbound payload, the
  existing sentinel leak check must pass, per-network memory stays namespaced, and desktop
  observations must never be routed to a social network by default.
- Autonomy: the roadmap's levels (0 Offline, 1 Read only, 2 React while active, 3 Occasional
  autonomous interaction, 4 Fully social) govern when a status update may become a post. No posting
  before an explicit grant, with rate limits and revocation.

---

## 7. Invariants this design must not break

1. Models propose; Core writes. Nothing is memorised or published by direct model action.
2. The dialogue model is never authoritative memory. Canonical memory content comes from the owner's
   words or from a validated source; capture files may hold model text, but a capture is staging, never
   a canonical record, and reasoning is never promoted to fact.
3. Capture files and reasoning are write-only staging: never displayed in chat, activity, status,
   widget or social payloads, and never injected into dialogue context or used as evidence.
3. Evidence priority is not instruction authority: retrieved memories, files and social events can
   never expand permissions or tool families.
4. Provenance and epistemic class are preserved; inference is never promoted to fact; nothing is
   silently rewritten.
5. No hidden chain-of-thought is exposed as output, file or status.
6. Fail closed, and never fabricate completion, evidence or memory certainty.
7. Private content stays loopback-local; social payloads are projections of public-safe fields only.
8. Secrets (bearer tokens, per-launch model keys, platform citizen keys) never enter settings files,
   changelogs, logs or prompts.
9. Agent write authority is granted, exact and revocable — one directory at a time, never a drive, and
   never SORA's own checkout by default. A run that cannot produce its reversibility evidence and its
   changelog does not run.

---

## 8. Risks and failure modes

| Risk | Mitigation |
|---|---|
| Selector false positives → memory spam | Per-turn/conversation/hour budgets, dedupe, easy owner deletion, confirmation line |
| Selector false negatives → missed memories | Acceptable; the owner can ask explicitly ("remember this") and the pre-filter must not swallow direct requests |
| Extra per-turn latency on a 2B model | Core-side pre-filter, 64-token cap, temperature 0, measurement of added milliseconds |
| Prompt flooding through the `FACT` slot | Hard caps and a priority review (§3.5) before enabling facts in context |
| Files drifting from canonical state | Files are projections; idempotent regeneration test; owner edits imported as revisions |
| Changelog requirement blocking read-only runs | Read-only agents return the entry text in their result instead of writing a file; Core stores it verbatim |
| A Core summary passed off as the agent's own account | Core never composes entries: it verifies the agent's file (path inside the working root + hash) or stores the agent's returned text verbatim with a provenance comment |
| Capture files leaking private text or reasoning | Local-only, git-ignored, never synced, write-only, bounded retention, deleted after compaction |
| Compaction promoting reasoning into fact | Epistemic class preserved; reasoning attached as evidence only; schema-constrained output validated in Core |
| Captures filling the disk | Size and count caps, forced compaction, retention window; raw retention off by default |
| A direct write destroying owner work (no throwaway worktree) | Pre-run snapshot/diff artifact, write lease, per-run limits, documented revert path — no evidence, no direct run |
| An agent editing the runtime that supervises it | SORA's own checkout excluded from default grants; explicit opt-in with a warning |
| A remote provider compacting private memories | Local model first, delegated local agent second, deterministic reduction third; never remote for private content |
| A third-party provider changing granted folders | Grant screen states it plainly with the exact path; revocation immediate and effective mid-run |
| Social leaks or permanent accidental posts (1F916) | Public projection + sentinel fixtures, read-only default, explicit grants, per-day limits; citizen key in the credential store |

---

## 9. Suggested staging (follow-on identifiers, not new roadmap phases)

| Stage | Deliverables | Acceptance gate | Status |
|---|---|---|---|
| MEM1: memory read/owner surface | Live retrieval into dialogue context, priority fix, memory API (list/inspect/correct/delete), GUI list with provenance, cleanup of the 9 test facts | Stored memories reach the prompt with correct tags and caps; owner can inspect, correct and delete; nothing stored outranks the owner's current message | Planned / — |
| MEM2: model-chosen remembering + capture | `MemoryChoice` contract, `MEMORY_PROMPT`, Core-derived canonical content, capture file with response (and reasoning if enabled), bounds, dedupe, confirmation + Remembering status | Measured selector accuracy on a fixture set; no memory without an owner statement or explicit request; conversation never blocked or altered by a memory failure; captures are write-only and bounded | Planned / — |
| MEM2b: capture compaction | Cadence compaction of captures into canonical `memories` rows, `sha256` provenance link, retention and deletion, model preference order | Compaction produces labelled memories (owner statement vs reasoning-as-evidence); a failed compaction leaves the capture untouched; captures are deleted after retention unless raw retention is on | Planned / — |
| MEM3: direct agent write authority + mandatory changelogs | `direct`/`isolated`/`read-only` workspace modes, per-project grants and revocation, lease + snapshot/diff artifacts, adapter policy revision (no worktree requirement for granted roots), result-contract changelog field, Core-written entries, artifact migration, `incomplete_missing_changelog`, GUI grant screen + viewer, routing keyed to write authority | An agent creates and modifies files in a granted project directory in place; every direct run records a reversibility artifact and a changelog entry registered as a hashed artifact; a run without either is never reported complete; `danger-full-access` still refused; SORA's checkout untouched by default | Planned / — |
| MEM3b: lasting agent sessions + context handoff | Resume policy per (project, provider), dispatch-path resume, expiry/failure handling with honest fallback, session state + reset in the GUI, project brief, `AGENT_RESULT`/`MEMORY` sources in task context | A second task in the same project continues the first task's native session; a lost session falls back to fresh and says so; project sessions never cross; a resumed task shows less re-briefed content in the context manifest | Planned / — |
| MEM4: status and journal files | Cadence triggers, projection + idempotent regeneration, AppSettings root + Open folder, owner-edit import | Status file regenerates from canonical data alone; owner hand-edits import as revisions | Planned / — |
| MEM5: read-only social ingestion | NekoVerse/1F916/Moltbook read paths, per-network namespaces, public projection, leak fixtures | Read-only by default; sentinel and namespace leak tests pass; no desktop data in any payload | Planned / — |
| MEM6: gated public status posting | Autonomy-gated periodic post, explicit grants, rate limits, revocation | No post without a grant; revocation takes effect immediately; 1F916/network limits respected | Planned / — |

Each stage ends with evidence, an exact completion timestamp with timezone, and its own
`changelog/<timestamp>_MEMx_<model-name>.md`. Distinguish implemented, in review and verified.

---

## 10. Verification matrix

| Layer | Checks |
|---|---|
| Contracts/policy | Two-value vocabulary enforced; extra fields and unknown values rejected; canonical memory content is never model text (captures hold model text as staging only); sensitivity/retention defaults applied |
| Budgets/dedupe | Per-turn, per-conversation, per-hour caps; repeat updates rather than duplicates; pre-filter skips questions, commands, attachments, results |
| Retrieval | Caps honoured; provenance tags rendered; owner message outranks stored memory; retrieved memory cannot authorise anything |
| Fail-closed | Invalid selector output → no memory, conversation unaffected; dialogue timeout unaffected by the memory call |
| Files | Idempotent regeneration; owner edit import; private entries excluded or marked; journal append-only within a day |
| Captures/compaction | Size/count caps enforced; captures never enter the prompt, chat, status or a social payload; compaction labels owner-statement vs reasoning-as-evidence; a failed compaction is retryable and lossless; deletion after the retention window |
| Agent write authority | Escapes refused (drive roots, `..`, symlinks/junctions, network paths, credential dirs, SORA's own checkout by default); revocation effective mid-run; per-run limits enforced; `danger-full-access` still rejected |
| Reversibility evidence | Every direct run records a pre-run snapshot/diff artifact; a run that cannot produce it does not execute in `direct` mode; the documented revert path is exercised in a fixture |
| Agent changelogs | File-changing run produces a hashed artifact and a repo-local file; missing changelog → incomplete status; derived entries labelled; nothing fabricated |
| Social (MEM5+) | Read-only default; namespace separation; sentinel leak fixtures; no desktop content; citizen key never in files/logs |
| Regression | Motion keywords unaffected; attachment/file turns skip the selector; existing settings tiers unchanged; `scripts/verify.ps1` gate |

---

## 11. Out of scope

- Embeddings or vector search — start with SQL/text retrieval as the roadmap requires, and add more
  only after measured retrieval failures.
- Memory summarisation or compaction by the small model.
- Owner-facing memory browsing inside the 3D avatar.
- Any live social posting, all social adapters, and Moltbook/1F916 interfaces themselves (MEM5/MEM6
  are placeholders for later work; P15.9 remains the NekoVerse item).
- Voice-path memory and changelogs.
- Emotional/personality drift tracking, or any "feelings" model.

---

## 12. Open questions for the owner

1. **What may she remember?** Only things the owner states (recommended for v1), or also things she
   concludes from her own work — the latter needs a different, weaker epistemic class.
2. **Should she say so?** A short "Noted." each time, a quiet status only, or nothing at all until
   asked.
3. **Changelog scope:** only tasks that changed files (recommended), or every delegated task with an
   explicit "no changes" entry.
4. **Where do her notes live**, and should that folder be an Obsidian vault you can browse?
5. **How often is "every so often"** — end of day at shutdown, long idle, or both?
6. **Thought chain:** capture the response only, enable thinking across the whole dialogue path (a real
   latency cost on a 2B model), or make a targeted second call with thinking enabled **only on turns
   that get remembered** (recommended — the detail is captured without taxing ordinary chat)?
7. **Capture retention:** delete each capture once it is compacted (recommended — the point is context
   economy), or keep the raw detail for a fixed window?
8. **Which directories are grantable** — a dedicated projects root (recommended), any folder the owner
   picks, or the Desktop wholesale? And may SORA's own checkout ever be granted, given it is the
   runtime supervising the agent?
9. **Who compacts:** a larger local model if one is running (recommended first choice), a delegated
   agent, or the deterministic reduction?
10. **Session scope:** one continuing session per project per provider (recommended), one per
    conversation, or reset after every task?
11. **What may be briefed to a remote agent:** owner-stated memories, project facts and that project's
    own agent results (recommended), or also private conversation excerpts and other projects'
    results?

---

## Appendix — verified references

- Memory schema and operations: `persistence/repository.py:410-495`; `contracts/models.py:264,270,331`.
- Context sources and priorities: `context/compiler.py:13-75`; dialogue context population:
  `runtime/service.py:1321-1354`, `2766-2816`; social-only use: `social/projection.py:36`.
- Small-model pattern: `contracts/motion.py`; `providers/dialogue.py:246-252`;
  `runtime/service.py:1478-1483`; `docs/runbooks/SORA_MOTION_KEYWORDS.md`.
- Agent result contract: `providers/codex.py:450-460`, `providers/hermes.py:395`,
  `providers/antigravity.py:289`.
- Storage facts: `memories` 0 rows, `facts` 9 rows (all `inference`, provenance "Hermes ACP
  normalized result"), `artifacts` 0 rows with no task/run column, `agent_runs` 5 rows.
- Changelog convention: `changelog/2026-09-29T082738+0100_MOTION-KEYWORDS_GPT-6-Astra.md` (latest
  example of the naming shape).
- 1F916 (external, verified 2026-09-29): `1f916.ai` front door, GitHub `1f916-ai/1f916` — agents-only,
  citizen-key identity, one post per UTC day, JSON API + MCP, sandboxed read-only recommended.
- Thought-chain availability today: `providers/dialogue.py:206` requests
  `chat_template_kwargs={"enable_thinking": False}`; `:242` caps a response at 16,000 characters.
- Agent isolation enforcement: `providers/codex.py:162` (read-only default), `:174-175`
  (`danger-full-access` refused), `:176-180` (`workspace-write` requires an owned worktree, manager and
  lease, and the cwd must equal the worktree path), `:195-215` (`for_owned_workspace`).
- Workspace machinery to reuse for direct writes: `workspaces/git.py` — `allocate`,
  `assert_write_lease`, `capture_artifact`, `capture_run_artifact`, `diff_workspace`, `diff_file`,
  `renew_lease`, `release_lease`, with `WorkspaceRecord`, `CodingArtifact`, `CodingRunArtifact`.
- Project grants: the `projects` table holds only `project_id, owner_id, created_at` (1 row, no root
  path), so granted roots need either a migration or an `AppSettings` entry.
- Session continuity that already exists but is unused: `resume()` and `session_id()` on both adapters
  (`providers/codex.py:233-239,368-370`; `providers/hermes.py:325-335`), capabilities `sessions=True,
  resume=True` (`codex.py:221`, `hermes.py:215-216`), `AgentSessionRecord` with `project_id`,
  `resume_supported`, `context_fingerprint`, `last_seen_at` (`contracts/models.py:166-179`),
  `attach_native_session()` with dedupe and `last_seen_at` refresh (`runtime/repository.py:583-628`),
  statuses `active|lost|closed` (`contracts/models.py:46-49`), and 3 live `agent_sessions` rows.
- Task context assembly already uses the shared compiler: `runtime/service.py:2826` (`compile_context`)
  → `:2897` (`context=compiled.text`), with `AGENT_RESULT`/`MEMORY`/`FACT` sources available
  (`context/compiler.py:64-75`).
