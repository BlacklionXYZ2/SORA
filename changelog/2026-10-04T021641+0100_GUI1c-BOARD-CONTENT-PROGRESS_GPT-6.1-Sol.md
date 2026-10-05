# GUI-1c Board / Content / Integrations progress — GPT-6.1 Sol

Model name: **GPT-6.1 Sol**. Implementation/verification checkpoint: **2026-10-04 02:16:41 +01:00**, Europe/London. Status: **implemented slice / GUI-1c in progress**. No full-stage completion time.

## Implemented changes

- Adapted the compatibility note board to injected shared projection/API/workflow and host hide/dispose/pending-work lifecycle; removed its duplicate Start-planned synchronizer. Added native keyboard-expand/collapse, responsive lane/card/control handling, readable agent/run labels and high-contrast source fallback.
- Added process-local BoardNoteDraft with stable request identity, captured assignee/Core epoch, partial-admission retention and explicit submitted-draft restoration. Assignment is version-checked, never auto-overwrites another writer; note placement/removal remain separate from task/run status.
- Completed the narrow shared retained projection/request adapter with shape/ID validation, stale cache, fixed routes, exact version/registered-target preflight, profile/epoch/write serialization, acknowledgement checks and unknown retry protection. No extra panel polling/store/runtime or automatic effect replay.
- Added registered Content navigation and read-only integration/capability/provider metadata inspector, inert paths and truthful failed/unsupported/limited/unknown results. No generic launcher, credentials editor or recurring local grant requests.
- Wired Board/Content/Integrations into tray/menu/Chat More/profile commands/root/full launchers, UI-only placement/mode state, and host Quit/disposal. Existing UI stores without the new field remain valid; AppSettings v9/default Desktop/owner runtime are unchanged.
- Added27 C# component cases, including durable UI-only store round-trip and original-preserving old-store reads; expanded the effect-free launcher verifier. Updated roadmap v1.16, host/interface introduction, runbook and verification record.

## Verification and limits

**192 C# passed**, **704 Python passed /25 opt-in skipped in85.63s**, **8 PWA passed**, mypy263/lint/schema/compile and all three zero-warning/error Windows builds. Final launcher forwarding passed. [Detailed evidence](../docs/verification/GUI1_BOARD_CONTENT_GPT-6.1-Sol_2026-10-04.md) preserves final-source/environment distinctions.

Actual fixture Core readiness/normal shutdown occurred, but the combined board-seeding/GUI-launch command was rejected by execution policy before it ran. No native GUI operation/capture or actual board/navigation admission occurred, and no bypass was attempted. Computer Use guidance required respecting that boundary; user-side/physical acceptance remains open. Fixture exited normally0, port18795 has no listener, owner Core PID52000/start unchanged. No private-file read, real/paid provider call, force kill, commit/reset or owner-setting mutation.

GUI-1c remains open for native retained-workflow acceptance, full run-history/artifact/public-chip parity and earlier lifecycle/Chat/physical gates. Voice/full Settings/Memory/scheduler/graph/ordinary release remain later required work. Original GUI references/overview/earlier draft/model attribution and GUI-0 completion timestamps are preserved.

## Source groups

Shared/compatibility: `FullAppModel.cs`, new `BoardNoteDraft.cs`, `KanbanBoardForm.cs`, desktop-app project links.

Host: `ShellSession.cs`, `RetainedRequests.cs`, new `RetainedBrowserForm.cs`, `ShellHost.cs`, `ShellForm.cs`, command/profile/IPC/preference/placement files and shell project links.

Launch/tests: root/full launcher enums, `verify-shell-launchers.ps1`, new `ShellRetainedTests.cs`, preference tests and C# project links. No Python/Core/contract/migration changes.

## Documentation/preservation read-back

At **2026-10-04 02:21:32 +01:00**, **106 local links** in the five updated/new roadmap/specification/runbook/verification/log documents resolve; all five supplied design assets match their manifest, three launcher/verifier PowerShell ASTs parse, and exactly the original GUI-0a/0c/0d completion times remain unchanged. A separate nine-original byte-size/SHA-256 comparison also passed for the overview, earlier GUI draft and full reference folder. No new GUI-stage completion is implied.

**Final-source addendum, 2026-10-04 02:23:10 +01:00:** Quit now summons the actual pending Board/Content/Integrations/Paths surface instead of unrelated Agents, and recovered UI preferences apply their board mode without losing process-local drafts. All three final product builds again have zero warnings/errors; all192 C# checks passed after these refinements. Listener count on18795 is again0. These host-only refinements have build/regression evidence, not native focus/recovery acceptance.
