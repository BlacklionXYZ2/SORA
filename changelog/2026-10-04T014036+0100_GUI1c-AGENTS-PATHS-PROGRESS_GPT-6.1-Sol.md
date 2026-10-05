# GUI-1c Agents/delegation and Paths progress — GPT-6.1 Sol

Model name: **GPT-6.1 Sol**. Implementation/verification checkpoint **2026-10-04 01:40:36 +01:00**, Europe/London. Status: **implemented slice / GUI-1c in progress**. No whole-stage completion time.

## Implemented changes

- Reused AgentCatalogueForm/ModelPurposeForm/ProjectPathsForm through `IAgentWorkflow`; ShellSession forwards via its existing WidgetSync/API with profile/Core-epoch/host guards. Compatibility clients retain their existing shared dialogs. No extra connection/state store/panel poller/provider worker.
- Added retained Agents task draft, metadata-only cached-list control, explicit discovery disclosure, exact provider/model/effort/project/mode selection and honest base-ref/deadline/capability/purpose details. Revision-checked purposes save only one agent's rows; hosted full Settings remains undelivered.
- Pinned uncertain submission body/key/Core instance, explicit identical retry only, no automatic replay or silent changed model/project. Known pre-admission invalid input permits correction; confirmed drafts require New task. Receipts separate reported admission/requested fields from execution proof.
- Reused canonical Paths reservation/event/coverage projection and explicit stopped-writer reconciliation. Added hosted hide retention, stale/offline availability, idempotent disposal and mutation/pending-work Quit guards; task controls share serialization.
- Wired both panels through tray, command menu, Chat More, profile IPC/direct options and root/full launcher enums/forwarding. Added UI-only placement keys without changing canonical settings version or default client.
- Fixed the initial stale connection label found in actual native inspection and prevented disappeared agents from silently becoming Automatic; no enabled specialist prevents automatic task start.
- Added17 deterministic C# cases and extended the effect-free real-launcher AST verifier for Agents/Paths. Updated roadmap v1.14, ownership notes, runbook and linked verification report.

## Source groups

Shared: `clients/desktop_widget/WidgetCore.cs`, `AgentCatalogueForm.cs`, `ProjectPathsForm.cs`.

Host: `clients/desktop_shell/ShellSession.cs`, `ShellHost.cs`, `ShellForm.cs`, `ActivityForm.cs`, `CommandMenuForm.cs`, `ShellProfile.cs`, `ShellInstance.cs`, `ShellPreferences.cs`, `PanelPreferencesBinding.cs`, `desktop_shell.csproj`.

Launch/tests: root `Start-SORA.ps1`, `scripts/start-full-sora.ps1`, `scripts/verify-shell-launchers.ps1`, `clients/csharp_tests/ShellAgentWorkflowTests.cs`. No Core/public contract/migration change, ordinary default switch, commit/reset or owner-service/configuration mutation.

## Verification and unresolved work

**165 C# passed**, **704 Python passed /25 opt-in skipped in84.83s**, **8 PWA passed**, mypy263/lint/schema/compile passed; all three Windows builds zero warnings/errors. Final source/launcher checks and precise evidence in the [verification report](../docs/verification/GUI1_AGENTS_PATHS_GPT-6.1-Sol_2026-10-04.md).

Actual isolated native cached/empty/offline projections with model down were inspected. Two native cached-list activation attempts failed; inputs stopped as required by the Computer Use skill. No successful user-side task submission, purpose save, writer recheck, picker/keyboard/hide retention or live provider execution is claimed. The final inert receipt-detail addition was built/tested after captures; the fixture had no receipt. All QA hosts/Core exited normally; owner Core PID52000/start unchanged, no paid probe/private-file read. QA artifacts retained under ignored `.local`.

GUI-1c remains open: finish expanding note board, registered Content/integrations, run history/artifacts/public chips and retained-workflow native/provider acceptance. Earlier lifecycle/Chat/physical gates, voice/full Settings/Memory/scheduler/graph/ordinary release are not waived. Existing GUI-0 completion timestamps and all contributor/reference originals are preserved.

**Documentation/preservation read-back, 2026-10-04 01:45:00 +01:00:** nine original documents/reference files retain their pre-edit byte sizes/hashes;96 local Markdown links in the five updated/new documents resolve; exactly GUI-0a/0c/0d remain checked with unchanged 19:24:55 completion times; root/full/forwarding PowerShell ASTs parse. Fresh source builds/tests are recorded above; this read-back does not create another runtime/GUI-stage completion.

[Roadmap](../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Host runbook](../docs/runbooks/SORA_DESKTOP_SHELL.md) · [Verification](../docs/verification/GUI1_AGENTS_PATHS_GPT-6.1-Sol_2026-10-04.md).
