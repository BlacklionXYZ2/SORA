# SORA — Vision alignment plan

**Status: PLAN ONLY. Nothing in this document is implemented.**
Author: Hermes (deepseek-flash), 2026-10-01 12:37 BST.
Baseline reviewed live against the running instance: 2026-10-01, `.local/manual-test`, Core port 18769,
state revision 27991, 13 tasks, avatar renderer `connected: true`.
Supersedes nothing. Absorbs `docs/plans/WINDOWS-NATIVE-PERCEPTION-AND-READ-TOOLS_2026-09-29.md` (§6 W4).

---

## 0. Owner's requirement, verbatim

> "create a plan to update SORA to fit the vision closer, including all the model decisions and removing
> a lot of the arbitrary and pointless security features. SORA should not have to apply to use tools and
> search files. The agents shouldn't either, but there should be a log of the paths each are working into
> that they don't cross while working."

Three deliverables are implied and all three are in scope: a closer fit to `SORA_OVERVIEW.md`,
an explicit model roster, and a trust/permission redesign with a **path ledger** replacing
per-operation permission applications.

## 1. Decisions taken

The owner was offered four choices and did not answer them, so these are the recommended options
recorded as decisions. Each is explicitly reversible — §12 lists them as the only open questions.

| # | Decision | Rationale |
|---|---|---|
| D1 | **Local-first models.** Gemma 4 E2B (managed llama.cpp) owns dialogue, vision and every classifier. Cloud models are used only for reasoning (Hermes / Codex / Antigravity). GPT-5.6 Luna stays available as an opt-in dialogue backend through the existing `external` settings block, off by default. | Owner's quota is the scarce resource; the live instance already runs this way. |
| D2 | **Owner-local = full trust.** One standing capability profile for the owner device, with per-class switches in Settings defaulting ON. Approval records and per-target grant strings are no longer required on the owner's own machine. Remote paired devices keep exact scoping. OS-effect postconditions stay. | Removes the "apply to use a tool" ceremony without removing the audit trail or the two guards that are correctness, not security (§3.4). |
| D3 | **Ledger: log everything, block crossings.** Every path a run reads or writes is recorded; writes outside the run's own declared root are refused, and two live runs may not hold overlapping writable roots. | Literal reading of the owner's sentence: "a log of the paths each are working into that they don't cross while working". |
| D4 | **Scope: all six workstreams** — trust, ledger, chat→desktop action, perception/read-tools, voice in the Windows clients, proactivity + GUI truth. | The critique found them interdependent; the flagship demo needs W3 and W4 together. |

## 2. Verified current state (read-only, live, 2026-10-01)

**Live instance.** Core `--serve --api-port 18769`, launcher-built helpers `--windows-capture
--windows-bridge --windows-action --windows-type`, embodiment player `clients/unity/Builds/Windows/SORA.exe`.
Dialogue resolves from `.local/manual-test/data/sora-settings.json`: `dialogue.backend = managed-llama`,
`llama.model_path = …gemma-4-E2B-it-IQ4_XS.gguf`, `mmproj_path = …mmproj-F16.gguf`, `context_size 8192`,
port 18771, `runtime.worker_count 2`.

**Avatar.** `GET /api/v1/projections/embodiment` → `connected: true`, `visible: true`,
`presentation_state: idle`, `current_position {x: 3640, y: 2087}` on `DISPLAY1` (3840×2160 @1.5 DPI;
`DISPLAY6` 1280×1024 @1.0 at x=-1280). Verified rendering via the runtime's own capture helper
(`clients/windows_capture`, `--list-monitors` + region capture). Newest physical-feedback event is
`poked` at 2026-09-29T20:58Z — no avatar event in ~40 hours.

**GUI.** Full app `clients/desktop_app/FullAppForm.cs` (802 lines, six pages: Chat, Activity, Content,
Integrations, Settings, 3D companion) and widget `clients/desktop_widget/WidgetForm.cs`. Both captured
live this session. Defects confirmed on screen, not inferred: raw Markdown printed literally in both
transcripts (`*  **Main Workspace:**`); widget "Ready to talk" beside `hermes · codex` while the
answering model is local Gemma; widget "Reference" label overlapped by its input; widget hint still
reads "Ctrl+E expand" while expanded; full-app footer stuck on a stale "Sent to SORA.".

**Two companion states disagree.** Reproduced 3× within seconds: `GET /api/v1/companion` returns
`state: "idle"` while `GET /api/v1/projections/companion` returns `state: "talking"` at the same instant.

**Trust path.** Every operation resolves through `resolve_operation_authorization`
(`src/sora/security/operations.py:85`), which demands a persisted grant **and** a linked
`ApprovalRequest` in `APPROVED` state (`operations.py:97-111`), then takes its single decision from
`authorize()` (`src/sora/security/policy.py:61`, called at `operations.py:120`). Grant consumption is
bounded by `max_uses` (`policy.py:77`, `capabilities/dispatch.py:46-54`,
`persistence/repository.py:648-653`). The runtime already self-mints one grant for its own flow
(`src/sora/runtime/service.py:1804`, a 30-second single-use capture grant) — the precedent D2 generalises.
There is **no approval UI**; grants must be minted out of band (acceptance tests use
`tests/authorization_helpers.persist_operation_grant`).

**Capability classes already exist** as `CapabilityOperation`
(`src/sora/contracts/models.py:86`): `tool.invoke`, `path.read`, `path.write`, `desktop.observe`,
`desktop.present`, `desktop.navigate`, `desktop.interact`, `voice.session`. D2 maps Settings switches
1:1 onto this enum — no new taxonomy is needed.

**Model-facing vocabulary today** (`src/sora/contracts/motion.py:7`) is one enum:
`none | wave | sit | lean | climb | stand | walk`, selected at `service.py:1522-1532`, described to the
model by the `[CORE ACTION NOTE]` at `service.py:1539`. Everything else (press, type, navigate, target
acquire) is API-only and grant-gated.

**No embedding/vector retrieval exists anywhere** in `src/sora` (searched `embedding|vector|cosine|
sentence_transformers|recall` — zero hits). Memory recall is not semantic today.

**Voice** exists as Core sessions + a deterministic client fixture (`src/sora/voice/`,
`tests/voice/test_sessions.py`, `scripts/benchmark-voice.py`). **Neither Windows client has any
voice surface**; the only mic button in the product is the PWA's, and it calls the browser's cloud
speech-recognition service (`src/sora/pwa/app.js:167-206`).

**Agent workspace isolation** exists for writes: `WorkspaceRecord` (`src/sora/workspaces/git.py:40`)
with `repository_root`, `worktree_path`, `lease_owner`, `lease_expires_at`; Codex refuses
`workspace-write` without an owned worktree and lease (`src/sora/providers/codex.py:198-207`), Hermes
likewise (`src/sora/providers/hermes.py:192-207`). Nothing logs or constrains what a run *reads*.

---

## 3. W1 — Trust simplification

### 3.1 Target behaviour

Owner-local requests are authorised by **policy**, not by paperwork. A remote paired device is
unchanged: exact scopes, exact grants, sessions.

### 3.2 Design

1. **New standing profile** in the settings file (`version: 3`): `trust.owner` — a map of the eight
   `CapabilityOperation` values to booleans, all `true` by default for the owner-local device id.
   Stored in `sora-settings.json` (owner-editable, versioned like every other section), surfaced in
   Settings → Trust (new section, §8.4).
2. **Fast path in `resolve_operation_authorization`** (`operations.py:85`): when
   `device_id` is the owner-local device *and* `trust.owner[operation]` is true, synthesise an
   ephemeral, request-scoped `CapabilityGrant` (status ACTIVE, no `max_uses`, owner/device/project
   matching), skip the approval lookup, and still call `authorize()` so the decision is recorded with
   a new `DecisionReason.OWNER_POLICY`. **No call site changes**: the seam is one function.
3. **Drop the grant header requirement on owner-local routes.** `routes.py` currently reads
   `X-SORA-GRANT-ID` at ~8 sites (`routes.py:763, 805, 975, 1141, 1161, 1192, 1479, 1549`). Each either
   keeps accepting a supplied grant (remote path) or falls through to the owner policy.
4. **Remove per-target grant strings for owner-local** (`desktop.present:<target_id>`,
   `desktop.capture:region:<rev>:<x>,<y>,<w>,<h>`, `desktop.observe:<pid>`,
   `desktop.interact:<target_id>:press|type`) — the class switch governs them. Keep the *target
   validation* (identity recheck, geometry recheck, topology revision) because that is staleness
   defence, not permission.
5. **Delete the Content grant-ID box** (`FullAppForm.cs:27-29`, placeholder
   "Existing content-navigation grant ID (never saved)") in favour of an ordinary file/folder picker
   under owner trust.
6. **What stays, with reasons stated in the code comments:**
   - `press`/`type` **postconditions and never-replay** (`expected_name_after`, `attempt_id`
     idempotency, bounded VALUE worker). These prove an effect happened and prevent a double-click;
     removing them would turn "pressed" into an unfalsifiable claim.
   - **Remote device scoping** (`X-SORA-DEVICE-ID`, session scopes, exact origins).
   - **Confirmation for destructive/irreversible actions**: delete, purge, uninstall, external publish,
     spend. These are "corrective choices stay owner-only" and are *not* part of the ceremony being
     removed.
   - **Secrets never logged**, credentials never in the settings file.
   - The **audit record**: every decision still writes a row (grant id, operation, resource, reason).

### 3.3 Files touched

`src/sora/security/policy.py` (new `DecisionReason.OWNER_POLICY`), `src/sora/security/operations.py`
(fast path), `src/sora/api/routes.py` (header optionality), `src/sora/runtime/service.py`
(owner-policy construction + capture mint at `:1804` superseded), `src/sora/runtime/app_settings.py`
(`trust` section, version 3 + migration), `clients/desktop_app/FullAppForm.cs` +
`clients/desktop_widget/*` (drop grant-ID fields), `docs/runbooks/SORA_SETTINGS.md` (inventory update).

### 3.4 Acceptance

- On the owner device, every capability class works with **no** grant file, approval row or header.
- With `trust.owner["desktop.interact"] = false`, press/type fail closed with a readable reason while
  everything else keeps working.
- A remote session with a valid paired device but no scopes still fails closed on every class.
- Every owner-policy decision appears in the audit projection with reason `owner_policy`.
- `tests/authorization_helpers` is no longer needed by any non-remote acceptance test.

---

## 4. W2 — Path ledger (the no-crossing rule)

### 4.1 Target behaviour

A run announces where it works; Core logs every path it touches; a run cannot write outside its own
root, and two live runs cannot hold overlapping writable roots.

### 4.2 Design

New module `src/sora/ledger/` (contracts + service), two persisted tables, one in-memory index:

| Table | Columns |
|---|---|
| `path_leases` | `lease_id`, `run_id`, `task_id`, `root` (absolute), `mode` (`read`\|`write`), `owner_id`, `device_id`, `started_at`, `expires_at`, `closed_at`, `status` |
| `path_events` | `event_id`, `run_id`, `path`, `kind` (`read`\|`write`\|`delete`\|`denied`), `within_lease`, `at`, `detail` |

1. **Lease creation.** Every agent run creates a write lease at launch from its declared root: the
   Codex worktree (`WorkspaceRecord.worktree_path`), the Hermes `cwd`, the Antigravity chroot, or —
   for chat-driven file work — the owner-visible working directory. A read lease is created for the
   repository root that the run may inspect.
2. **Recording.** `read_local_file` (`src/sora/runtime/local_files.py:48`) and the agent adapters'
   file paths record `path_events`. Because the adapters are separate processes, the reliable record is
   (a) the path the runtime hands them, (b) their working root at launch, and (c) for Codex, the
   App Server's own file-change notifications; closed-loop coverage of every read inside another
   process is **not claimed** (§10).
3. **Enforcement.** A write is allowed iff `_path_is_within(path, own_lease.root)` (the helper already
   exists: `security/policy.py:46`) — otherwise denied and recorded, and any *live* lease whose root
   contains the same path makes it a **crossing**: denied with `crossing_run_id` in the event.
4. **Owner surface.** Activity gains a **Paths** column/panel: live leases, recent events, and a
   one-click "allow this path for this run" exception that writes a lease amendment — replacing the
   grant-ID workflow for file access.
5. **Interaction with worktrees.** Worktrees stay the mechanism for parallel *writes*
   (`workspaces/git.py`); the ledger adds what was missing: reads, shared trees, and a truthful record.

### 4.3 Files touched

`src/sora/ledger/*` (new), `src/sora/contracts/ledger.py` (new, exported via
`scripts/export-contracts.py`), `src/sora/workspaces/git.py` (lease at worktree creation),
`src/sora/providers/codex.py` + `hermes.py` + `antigravity.py` (declare root at launch),
`src/sora/runtime/local_files.py` (record + enforce), `src/sora/runtime/service.py` (run lifecycle),
`clients/desktop_app/FullAppForm.cs` (Paths panel), `clients/pwa` (read-only projection).

### 4.4 Acceptance

- A run writing inside its root succeeds; the same write outside it is refused with a readable reason
  and a `denied` ledger row.
- Two concurrent runs with overlapping roots: the second either waits or is refused; no interleaved
  writes.
- The Paths panel shows every event for a completed run after a Core restart (durability).
- A read of a file outside every lease is allowed but recorded (reads are logged, not blocked — D3).

---

## 5. W3 — Chat → desktop action (the flagship gap)

### 5.1 Target behaviour

`SORA, pause Spotify` in the owner-local chat walks her to the control, reaches, and presses it —
with a verified postcondition — instead of answering "I am unable to perform physical actions".

### 5.2 Design

1. **Widen the one-key vocabulary, not the authority.** `src/sora/contracts/motion.py` gains
   `type ActionKeyword = Literal["none","wave","sit","lean","climb","stand","walk","look","point","press","type"]`
   in a new `ActionChoice` contract alongside `MotionChoice`. The model still returns **one field**.
2. **Core supplies the candidates.** When the turn could be a desktop action, Core injects the
   currently-presentable targets into the note (`service.py:1539`) as a short list, e.g.
   `Spotify:Pause`, `Notepad:Save`. The model may name a target **by that label only**; it never
   supplies a window handle, bounding box, coordinate, grant or process id.
3. **Dispatch through the existing lifecycle.** `press` reuses the P11.3/§12.6 path: acquire target →
   `desktop.present` walk/turn → P11 interaction lifecycle → contact-revalidated press with
   `expected_name_after` → retract. `look`/`point` reuse the P12.6 affordance verbs.
4. **Acknowledgement stays honest.** The response says dispatch, never completion; a completion line is
   emitted only after the postcondition is read back.
5. **Skipping stays cheap.** Selection runs only on owner-local direct requests, after the existing
   pre-filter (no questions/greetings/attachments/result turns), with a tight output cap.
6. **Deterministic provider override.** "Ask Codex / have Hermes look at this" is parsed
   deterministically (alias table, no model call) into `router.route(explicit_provider=…)`
   (`src/sora/routing/router.py:123`).

### 5.3 Files touched

`src/sora/contracts/motion.py`, `scripts/export-contracts.py` (regenerate schemas),
`src/sora/providers/dialogue.py` + `llama_server.py` (selector), `src/sora/runtime/service.py`
(`_dialogue` + note), `src/sora/capabilities/*` (target list for the note), `docs/runbooks/SORA_MOTION_KEYWORDS.md`.

### 5.4 Acceptance

- Live: "pause Spotify" through `POST /api/v1/dialogue` against the running stack produces walk →
  reach → press, the media fixture flips playing → paused, and a UIA postcondition is recorded.
- Negative: "can you press buttons?", "don't pause it", a remote session, and an attachment turn all
  select `none` and dispatch nothing.
- Disconnected renderer: acknowledgement only, no completion claim.

---

## 6. W4 — Perception and read tools (absorbs the pending perception plan)

1. **One-key perception enum** `none | window | tree | read` on the W3 selector: Core resolves the
   foreground window and returns the **structured UIA read** (names, types, rects) to context — the
   vision-first inversion the overview §25 forbids is corrected.
2. **Read/search commands in chat**, Core-side and deterministic: `read file <path>`,
   `list <dir>`, `search <pattern>` (bounded results, ledger-recorded). No grant application (W1),
   no model-chosen filesystem walk.
3. **Keep capture as an explicit door** (`dialogue_with_desktop_view`, `service.py:1736`) and keep the
   one-shot, discard-after-use rule.
4. **Evidence on screen-derived turns.** A vision turn must persist a reference (capture id, region,
   timestamp) in the assistant message metadata and the GUI shows it; a screen claim without a frame is
   not acceptable (the 2026-09-30 "video editing application" answer is the failure case).
5. **Launcher.** Any new helper goes into `scripts/start-full-sora.ps1` (one flag per capability) — the
   launcher is the owner's entry point and its banner lists every wired capability.

---

## 7. W5 — Voice in the Windows clients

1. **Widget and full app gain press-to-talk** using the existing P14 protocol: local Silero VAD,
   faster-whisper `base.en` int8, Kokoro v1.0 int8, PCM-driven mouth/emotion presentation.
2. **Reuse, don't re-invent:** the client seam is defined by `tests/voice/test_sessions.py` and the
   Core routes `POST /api/v1/voice/sessions*`. Add a C# client (`clients/voice_client/`) rather than
   extending the fixture.
3. **No cloud STT in the Windows clients.** The PWA's browser speech recognition stays labelled as
   possibly non-local.
4. **First real-device acceptance:** open an actual microphone and speaker and record the result —
   P14 has never claimed this.

---

## 8. W6 — Proactivity surface and GUI truth

1. **Proactivity becomes a setting, not an env var.** `SORA_AVATAR_PROACTIVITY` /
   `SORA_AVATAR_DISTRACTION_LIMIT` move into `app_settings` (`embodiment.proactivity`,
   `embodiment.distraction_limit`) and onto Settings.
2. **Event-driven proactivity** (overview §36): task completed / build failed / dialog appeared →
   Core may present `walk near + look + optional speech` from the P13.1 event stream, rate-limited and
   suppressible. This is the difference between ambient sway and proactivity.
3. **Status truth:** make `/api/v1/companion` and `/api/v1/projections/companion` derive from one
   source; label the answering dialogue model separately from available specialists in the widget header.
4. **Rendering:** render Markdown (or convert model output to plain text) in both clients; the raw
   `**bold**` seen today is a defect.
5. **Avatar controls:** restart / show-hide / re-centre / monitor picker / scale + renderer health in
   the 3D companion page (today: five pose buttons and a licence note), plus a VRM picker.
6. **Layout:** fix the "Reference"/input overlap, the 40px composer with oversized scrollbar arrows,
   the stale footer status, and the "Ctrl+E expand" hint when already expanded. Test at 100/150%
   DPI and on the mixed-DPI secondary display.

---

## 9. Model decisions (complete roster)

| Role | Model | Where it runs | Config key | Notes |
|---|---|---|---|---|
| Dialogue (default) | Gemma 4 E2B IQ4_XS + `mmproj-F16` | Local, managed llama.cpp :18771 | `dialogue.backend = managed-llama`, `llama.model_path`, `llama.mmproj_path` | 8192 ctx today; raise to 16384 if the note grows |
| Dialogue (optional) | GPT-5.6 Luna | LM Studio / OpenAI-compatible | `dialogue.backend = openai-compatible`, `external.model`, `external.base_url` | Off by default (quota) |
| Vision (screen description) | Same Gemma 4 E2B (mmproj) | Local | as above | No OCR pipeline; output is prose, so §6.4 applies |
| Classifiers (motion, action, screen, memory choice) | Same Gemma 4 E2B | Local | n/a — one small call per turn, temperature 0, JSON-constrained, tiny cap | Fail closed to `none`; pre-filter before calling |
| Memory retrieval | **None in this plan** — SQLite FTS5 + recency/priority scoring | Core | n/a | Deliberate: a local embedder (`bge-small-en-v1.5` GGUF via llama.cpp `/embeddings`) is the follow-up if FTS proves insufficient |
| Reasoning — general/research | Hermes (Sol / Astra) | Hermes ACP | `--provider hermes` | P04 |
| Reasoning — coding | GPT-5.6 Luna via Codex App Server | Codex | `--codex-model`, `--codex-write-base`, `--codex-workspace-root` | Low effort by default |
| Reasoning — alternative coding | gpt-oss-120b-medium | Antigravity | `--antigravity-model`, `--antigravity-effort` | Low effort |
| Router | Deterministic rules (no model) | Core | `router.route()` | Plus the deterministic alias table from §5.6 |
| VAD / STT / TTS | Silero VAD, faster-whisper `base.en` int8, Kokoro v1.0 int8 | Client-side | W5 | Benchmarked in P14.1; client never sends raw audio to Core |
| Lip sync | PCM RMS/noise-gate → VRM `aa` + coarse emotion | Client-side | P14.4 | Unchanged |

**Rule that keeps this affordable:** the model decides *whether*; Core supplies *what, where and how
much*. Every added classifier call must be pre-filtered and its latency measured, not assumed.

---

## 10. Failure modes and required behaviour

| Failure | Required behaviour |
|---|---|
| Owner policy file missing/unreadable | Fall back to **deny** for `desktop.interact`, `path.write`, `tool.invoke`; allow `desktop.observe`/`path.read`; say so in Settings |
| Lease expired but run still writing | Refuse the write, record `denied`, mark the run's status; never silently extend |
| Two runs claim the same writable root | Second is refused at launch with the first run's id — not a mid-run surprise |
| Adapter writes outside its root via its own tools | **Not interceptable in-process today** — record what the runtime handed it, and treat Codex worktree + App Server notifications as the coverage boundary. Do not claim closed-loop enforcement |
| Model selects an action with no presentable target | Fail closed to `none`, dispatch nothing, answer normally |
| Press postcondition not observed | Report failure honestly; never replay the attempt |
| Remote device with owner-trust settings | Owner policy is keyed to the owner-local device id only; remote keeps scoping |
| Vision turn with no frame reference | Refuse to store the claim as a screen observation; show the missing evidence in the GUI |
| Avatar renderer disconnected mid-action | Acknowledgement only; no completion; no queued replay on reconnect |

---

## 11. Test plan

- **Trust:** owner-policy allowed/denied per class; remote still exact-scope; audit rows written;
  destructive actions still confirmed. Existing `tests/authorization_helpers` flows become remote-only.
- **Ledger:** in-root write allowed, out-of-root refused, concurrent overlap refused, durability across
  restart, read-only events recorded, exception amendment works.
- **Action:** each keyword; strict JSON rejection; injected/extra fields rejected; no-target → `none`;
  revoked renderer; remote excluded; completion only after postcondition.
- **Perception:** window/tree/read enum paths; bounded results; ledger rows; no grant required locally.
- **Voice:** the existing deterministic fixture plus one real-device run recorded with evidence.
- **GUI:** DPI matrix (100/150%, mixed monitors), markdown rendering, status-truth assertions,
  layout-overlap regression checks.
- **Full gate:** `scripts/verify.ps1` plus `.\scripts\verify-p10.ps1 -Full` for the desktop paths, and a
  packaged-avatar live scenario as the acceptance record (P15.4 style).

---

## 12. Questions still owed an answer

1. **D1** — confirm the local-first roster, or name the model you want for dialogue.
2. **D2** — confirm owner-local full trust, or choose a narrower profile (e.g. keep `desktop.interact`
   confirmed every time).
3. **D3** — confirm that reads are logged but never blocked.
4. **Per-run sandbox vs. shared tree** — should chat-driven file work get its own lease root per task,
   or operate directly in the SORA repo?
5. **Memory retrieval** — accept FTS-first (no new model), or commit to a local embedder now?

## 13. Explicitly out of scope

Public/multi-user hosting; any change to the packaged-install/update flow beyond new settings keys;
LiveKit; mobile-native clients; any claim about animation quality (a separate acceptance track);
changing the `press`/`type` postcondition rules.

## 14. Deliverables and implementation order

1. **W1 trust** (smallest, unblocks everything) — one function, one settings section, one new reason.
2. **W2 ledger** — contracts + tables + panel.
3. **W3 action vocabulary** — flagship demo.
4. **W4 perception/read** — absorbs the pending perception plan.
5. **W6 GUI truth + proactivity** — visible payoff.
6. **W5 voice in the clients** — largest new surface, last.

Each step ships with its own acceptance run, a `changelog/` entry (agent-authored, hashed, verified),
and a verification doc under `docs/verification/`. The launcher gains one flag per new capability, and
its banner lists them.
