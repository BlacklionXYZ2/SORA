# GUI-1c retained Agents/delegation and Paths — verification

Model name: **GPT-6.1 Sol**. Checkpoint **2026-10-04 01:40:36 +01:00**, Europe/London. Status: **implemented slice / GUI-1c in progress**. No full-stage completion or ordinary default switch.

## Implementation

Existing AgentCatalogueForm/ModelPurposeForm/ProjectPathsForm now share `IAgentWorkflow`; WidgetSync implements it for compatibility clients and ShellSession supplies guarded forwarding over its one existing synchronizer/API. No per-panel full refresh, timer, HTTP client, store, provider or speech worker. Host tray/menu/Chat More/IPC/direct options and root/full launchers expose `agents` and `paths`. UI version1 recognizes seven panel keys; existing stores remain valid and older binaries encountering unfamiliar keys stay original-preserving/read-only.

The hosted agent selector has its own bounded task draft and exact model/effort/project/mode controls. Cached reads do not probe models; explicit Refresh retains disclosure. Actual saved base ref/capabilities/purposes are inspectable; deadline and base ref have no new per-task override. Existing purpose edits patch only the chosen agent's canonical model rows at the captured settings version/revision. Hosted Settings remains read-only and AppSettings remains v9.

Explicit submission retains text/body/key/Core epoch across uncertain replies; changing request/model/project with that key or crossing epochs is rejected. Only explicit same-body retry is allowed. Known `INVALID_INPUT` is validated before admission on this route and permits correction; other outcomes remain pinned. Confirmed drafts cannot duplicate the task and New task uses a new key. Receipt includes reported requested fields; missing fields are labelled. Admission is not execution proof.

Paths reads actual reservations/events and coverage/uncertainty notices; reconciliation is explicit, not force unlock. Both hosted panels hide on user close and retain process-local state; stale/offline/host-blocked effects fail closed. Reads cannot return another epoch's data as current. Secondary mutations serialize with independent Activity task controls; pending panel operations/purpose dialogs prevent native/IPC/delayed host Quit. Disposal is idempotent and cancels outstanding reads. An initial connection-label bug discovered during inspection was fixed; provider disappearance no longer silently resets explicit selection to Automatic. No enabled catalogue entry means Automatic cannot start a task.

## Fresh automated checks

| Command/environment | Result |
|---|---|
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **165 passed**, zero failed/skipped; final test run exit0 |
| `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` | **704 Python passed /25 opt-in skipped in84.83s**, **8 PWA passed**, mypy263/lint/schema/compile passed; exec80952 exit0 |
| Shell/Desktop/Widget `dotnet build ... --verbosity quiet` | all zero warnings/errors; final-source builds exit0 |
| `./scripts/verify-shell-launchers.ps1` | real full-launcher AST defaults/explicit selection/Activity/Agents/Paths/unsupported effort forwarding passed, effect-free receiver only |
| `git diff --check` | no whitespace-error diagnostics; existing LF→CRLF warnings only; Git does not validate untracked source |

**17 new C# cases (148→165)** cover cached reads with model down/no mutation, offline/host/disposed refusal, exact owner/model/effort/project/mode body independent of Chat, same-body explicit retry/no refresh replay, epoch mismatch, old-epoch acknowledgement/read refusal, mutation serialization, purpose-only revision patch, explicit probe/reconcile routes, known pre-admission rejection, frozen/confirmed draft keys, invalid acknowledgement, mismatched profile/host block during submission, and bounded Agents/Paths commands/placements.

Full Python/PWA run occurred after workflow/launcher changes but before later C#-only refinements; Python/Core/schema source was not changed afterwards. All three Windows clients and the final165 C# suite were rerun after final source. Final launcher forwarding was verified after both enum changes.

## Actual isolated GUI evidence and limitations

Fresh deterministic QA Core used `.local/gui1-agents-paths-20261004`, port18794, `--model-unavailable`. All file/desktop/voice/delegation capabilities remained disabled. Cached catalogue actually reported one `deterministic-mock` entry, `enabled:false`, `state:not_checked`; authenticated task list contained **zero tasks**. No real provider, model, discovery probe or private file was exercised.

Initial host PID22116 started01:30:35. An actual Agents screenshot/accessibility tree showed readable selectors/project/mode/task editor and metadata warnings, but exposed a stale initial-unavailable label after connection; corrected in source. Clicking Read cached list failed with **`failed to activate captured window`**. Fresh window selection/capture then one retry failed identically. Native inputs stopped per Computer Use skill; no blind typing, terminal UI or alternative UI automation.

After normal IPC Quit/build, intermediate host PID26200 started01:33:51 and was closed normally. Final inspected host PID54836 started01:34:41 with `--show none`, then panels were summoned through their actual profile IPC. Hidden process startup initially required a repeated summon for targetable windows; no duplicate service owner was created. Actual cached catalogue loaded on first visible panel open with Core ready; no discovery click was required. At144-DPI profile placement, final inspections showed:

- Agents: readable cached/default controls, separate task draft, no enabled specialist notice and disabled Start; connection status no longer incorrectly unavailable. First screenshot was occluded by Paths; separate unobstructed read-only capture subsequently showed the Agents layout. No dropdown selection, typing, submission, purpose edit or hide retention was operated successfully.
- Paths: actual empty canonical reservation/event grids, full coverage/uncertain-writer notice and reachable Refresh/Recheck controls. Empty synthetic data is not evidence of an observed real writer.
- After fixture STOP normal exit: Agent screenshot showed stale/offline status and disabled cached/probe/purpose/Start controls; an accessibility snapshot taken during transition was older than the screenshot, so do not treat that tree as simultaneous enabled-state proof. Later Paths screenshot/tree showed stale notice and disabled Refresh/Recheck consistently. No native button operation or recovery interaction was inferred.

The final receipt-detail-only addition was built/tested after these captures. There was no receipt in the native fixture, so no final receipt rendering/actual admission proof is claimed. Key/epoch/body guards and receipt failure behavior are component tests only.

Fixture exec87593 exited normally0 after its dedicated STOP sentinel. All three QA host PIDs absent and port18794 absent by **01:38:57 +01:00**. Owner Core **PID52000**, start **2026-09-29T21:49:32.7934609+01:00**, remained unchanged. No force kill, owner configuration/data mutation, paid call, commit or reset. Synthetic QA artifacts retained under ignored `.local`.

## Final fingerprints

| Source | SHA-256 |
|---|---|
| WidgetCore.cs | `DD2639DE6021306AD0D826E1F9A3EDC59CD5623561543BEF1414787FB10A84F7` |
| AgentCatalogueForm.cs | `F884524512E2BEC71E705AB868EC1B5BBE4AA2FDE0F7BA84EC10335635B52885` |
| ProjectPathsForm.cs | `DCCE5C3368768C1E5A32D9FCE53676D46F1BC7ED44E65E42163E3E5C447638AB` |
| ShellSession.cs | `5D282A4D4AC556AA4523A40A04843342662A11E15C6DF4653A0EEDC4BB3AE73E` |
| ShellHost.cs | `3504923EE1613B7B98D27D8FAB357C5B967E8EEA02DFAD1986C4AFA53BE83777` |
| ShellAgentWorkflowTests.cs | `0F691E1B99FA7A3CD9862CDBAF7B382ADEACC39FA8FE4E2F413D47911A035B6C` |

## Remaining gates

Native dropdown/model/project/task input, purpose-save/conflict/cancel/restart, explicit task submission/retry/receipt/evidence and Paths recheck, hide/reopen draft/selection retention; real configured provider entitlement/project boundary/writer evidence. Keyboard/screen reader/high contrast/text scaling/mixed monitor and final visual acceptance remain open. Component guards and actual empty/cached/offline projection do not substitute for these.

GUI-1c board/Content/integration/run-history/artifact/public-chip parity, GUI-1d voice, full GUI-2 Settings, canonical Memory/semantic presentation, persistent scheduler, real graph/final style and ordinary launch/release remain required, alongside earlier host/Chat/GUI-0b gates. No additional completion box/time.
