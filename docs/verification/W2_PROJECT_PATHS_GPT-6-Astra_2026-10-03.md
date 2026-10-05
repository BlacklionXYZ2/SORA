# W2 selected projects, writer lifetime and readable evidence — GPT-6 Astra

Delivery checkpoint: **2026-10-03 13:43:56 +01:00**, Europe/London.
Status: implemented progress slice with the evidence below; **W2 and the overall frontend goal
remain in progress**. This document does not replace any acceptance requirement in the plans.

## Implemented

- Canonical settings v8 adds per-agent project root, direct/isolated/read-only mode and Git base ref;
  v2–v7 migration retains the original backup. The existing shared Settings editor exposes them.
- Canonical runtime specialist deadline is editable in the GUI, defaults to 300 seconds, validates
  5–3600 and is captured at run admission. Legacy runtimes without canonical settings retain their
  existing configured deadline. In-flight tasks are not silently extended by preference changes.
- Per-task project/mode flows through the shared delegate dialog, board starts, API, task records,
  idempotency and provider requests. New tasks pin their destination/model preferences. Missing
  destination for local write work asks “Which project?”. There is no implicit SORA-root target.
- Direct work uses the actual selected folder and preserves existing dirty files. Isolated worktrees
  remain explicit opt-in; inspection can use read-only. Selecting SORA source for writes requires a
  SORA-specific intent. Canonical validation rejects relative, missing, UNC, drive and account roots.
- Only the Codex adapter currently has this selected-project boundary. Hermes/Antigravity requests
  with such a project return typed unsupported results, without silently changing the harness/model.
  Their general configured-agent execution is not replaced or globally disabled by this slice.
- Migration 10 adds durable path reservations and event evidence in the existing Core database.
  Reservation acquisition is atomic and detects equal/nested canonical Windows paths. Reservations
  do not expire into permission to overlap. Uncertainty retains the root; reconciliation consults
  owner-process/kernel-job evidence and will not clear a live Core's pre-launch reservation.
- Before any project-bound Codex writer starts, a real-base-Python waiting bootstrap is attached to
  a named non-breakaway Windows kill-on-close job. It receives the launch byte only after attachment.
  This avoids the venv/Windows execution-alias bootstrap escape observed during QA. Normal cleanup
  terminates the owned job and checks zero active members while its handle remains open, then closes.
- The per-thread native Codex policy permits the selected writable root, disables network and
  extra temporary roots, and leaves outside-root reads available. Configured MCP/app/browser/plugin/
  subagent integrations are disabled for that project-bound native thread because they are not
  proven to obey the same filesystem boundary. No owner-wide native-agent config is overwritten.
  This is sandbox configuration, not proof that a Windows job alone confines filesystem effects.
- Selected-project tasks receive a fresh native thread and focused task/reference context rather
  than an entire recent desktop conversation. No cross-project session resume or fallback occurs.
- Core cancel/steer now uses the actual bound adapter, not its unbound provider template. Codex
  cancellation attempts native interruption, then escalates boundedly for an unresponsive turn;
  stop evidence survives result consumption and is checked before normal reservation release.
- Bounded before/after size/mtime snapshots skip Git internals, symlinks and reparse points. Evidence
  labels distinguish declared roots, provider reports, filesystem metadata diffs and Core lifecycle.
  Incomplete snapshots are explicit; newly discovered files are not called newly created when the
  before-snapshot was incomplete. No file bodies are copied into the Paths ledger.
- Shared Windows **Project paths and writers** displays reservations and labelled evidence, with
  Refresh and conservative Recheck, no force-unlock. Activity includes requested project/mode and
  an explicit **View selected result** button. The readable result window shows stored failure,
  warnings, file/command reports, changelog report and coverage without requiring JSON decoding.
- Result/Paths endpoints are owner-local. Remote task lists and event-resync snapshots omit the new
  stored project/base-ref fields. This does not scrub arbitrary paths in existing user/provider text.
- Project fields and Browse disable while submission is in flight. GUI review repaired Activity
  wrapping, Paths table overflow, dialog DPI initialization and the clipped Browse label.

## Verification

Final `scripts/verify.ps1`, dedicated `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003`:
**608 Python passed / 24 opt-in skipped**, **119.42 seconds**, **8 PWA checks**. Ruff, mypy (248
source files), contract-export check and compileall passed. Contract export ran before the gate.
**41 C# tests** passed. Full app and compact widget build with **zero warnings/errors**.
The separate native-probe script passed Ruff and mypy with the local source tree included.

New selected-project/path tests exercise actual controlled App Server processes, in-place fixture
edits/dirty-file preservation, typed missing destination, remote path masking including event
resync, overlap/uncertainty, migration backup, bounded diff labels, pre-launch reservation retention,
dead-Core reconciliation against a still-live named job and release only after that job stops.
The stubborn-writer test ignores interrupt and starts a real child that changes a heartbeat file:
Core cancellation reaps it, leaves the heartbeat unchanged and releases the reservation afterward.
These are deterministic fixture checks, not paid model inference.

Native job tests retain the original descendant process handle and verify its signalled exit plus
zero job membership. Earlier full-suite attempts failed because reopening a terminating PID can
yield access-denied/unknown, and a missing job name after handle close is not a suitable assertion
for immediate descendant exit. The final test verifies the stronger retained-handle/kernel proof.
The PID helper intentionally remains conservative on unknown/access-denied; it is not weakened.

The initial stubborn fixture also inherited the server's protocol input/output. Giving its child
separate stdin and diagnostic output removed delayed startup. The cancellation assertions were
retained. Earlier failed test and probe artifacts were not erased to make the evidence look clean.

### Native sandbox, no inference

Command:
`uv run --locked python scripts/verify-project-boundary.py .local/project-boundary-qa-20261003-r8`

Actual installed Codex App Server accepted the per-thread overrides (one configured MCP integration
disabled for the QA thread). No turn/prompt inference was started. Native `command/exec` using the
same sandbox policy produced:

| Probe | Result |
|---|---|
| Write inside declared project | Exit 0; file exists |
| Write to outside fixture | Exit 1, access denied; original preserved |
| Read outside fixture | Exit 0; expected fixture text |
| Write through inside junction to outside directory | Exit 1, access denied; target unchanged |
| Write inside project using read-only policy | Exit 1, access denied; file absent |

Private evidence: `.local/project-boundary-qa-20261003-r8/boundary-proof.json`. Earlier r1–r7
attempts/proofs remain. This verifies native command enforcement for these cases, not every opaque
integration, kernel escape, alias type, crash timing or live-model outcome.

### Actual low-cost model attempt — failed, not verified completion

The isolated QA Core used **gpt-5.6-luna / low**, not Astra/high-cost inference, for one tiny direct
project edit. Task `task-b14fd1d4-3ca9-4e0c-9af1-e5e7a1c93788`, run
`run-22ba1d23-4ca7-4fd6-8682-6f7564a73d28`, state `.local/project-gui-qa-20261003`.

The actual fixture marker changed `before` → `after`, and a readable agent-authored file appeared at
`project/changelog/20261003_093435Z_marker-replacement_GPT-5.md`. But the old default **30-second
Core deadline** elapsed before final JSON. The run is **failed/timed_out**, and its missing reported
changelog is visibly incomplete evidence. Physical creation does not convert that task to success.
The agent's generic GPT-5 attribution is retained as historical evidence, not silently corrected.

The configurable 300-second canonical deadline and harness-selected attribution prompt were added
after this failure. A second live launch was blocked by the execution policy and was **not retried
through another channel**. No successful post-repair live-model completion is claimed. `.local`
contains an unused second marker fixture; it is not proof of a second model run.

### User-facing Computer Use

Owned full-app QA processes included 31348/50688 before the helper/session reset, then **30812**,
final rebuilt **54504**, loopback QA Core port **18793**. Only the isolated QA state/token/frontend
preferences were used. The existing owner Core **52000** was not restarted or reconfigured.

- Activity visibly shows failed status, requested Luna/low and actual project/direct mode.
- Explicit **View selected result** opens plain readable timed_out details, changelog_missing,
  requested root/model and honest coverage statement. It does not claim independent action proof.
- Paths shows no active reservations, the stored stop event and marker/changelog metadata changes.
  Rebuilt layout visibly includes all Source/Run columns and the wrapped coverage notice.
- Settings exposes the canonical project/mode/base-ref and new 300-second runtime control. This
  turn did not save those settings through the GUI or change security/privacy toggles.
- Final shared Delegate dialog visibly shows Project, fully readable Browse, Mode and bounded
  no-inference notice. Entering the QA directory works. **Cancel preserves the main composer draft**.
  Final dialog was cancelled; Start was not pressed. This is not successful GUI edit submission.
- Final QA windows were closed normally through Computer Use. The exact owned QA Core process
  chain 57688/22536/55312 was identity-checked and force-stopped; port 18793 was released. This is
  not graceful Core shutdown acceptance. Owner Core 52000 remained alive; QA files were retained.

## Remaining acceptance / next work

1. Successful ordinary GUI selected-project edit with final validated result, real model-name
   changelog verification/opening, and readable progress/follow-up/cancel/retry across both clients.
2. Full real Core crash/restart matrix, PID identity/reuse, live descendants, uncertain launch,
   canonical aliases/case/junction changes and conflicting parent/nested concurrent roots. The
   dead-Core/job fixture is not a full application restart acceptance test.
3. Owner-visible root amendments/renewals, richer declared principal/coverage schema, Core-mediated
   read-path ledger hooks and denied-operation records where the actual executor exposes them.
4. Isolated-mode GUI and source/worktree coordination matrix; implementation is not fresh complete
   user-side acceptance. Hermes/Antigravity boundaries must be developed and independently verified.
5. Editable multi-model purpose shortlist and SORA's 2B-facing CompanionCall delegation schema.
6. Remaining W1/W3/W4/W5/W6, PWA/project UX, native actions, real spoken voice, avatar/proactivity,
   memory inspection, mixed-DPI and final requirement-by-requirement frontend acceptance.

The owner’s existing Core has not loaded this source slice. Normal restart will be needed before
these new backend features appear there; no restart was performed on the owner’s behalf.

Sources for implementation decisions: [Codex App Server](https://learn.chatgpt.com/docs/app-server),
[Codex security](https://learn.chatgpt.com/docs/agent-approvals-security),
[Windows jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[WinForms scaling](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/forms/autoscale).
