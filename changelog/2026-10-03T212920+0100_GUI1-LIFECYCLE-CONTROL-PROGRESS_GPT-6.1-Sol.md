# GUI-1a managed lifecycle control progress — GPT-6.1 Sol

Model name: **GPT-6.1 Sol**. Implementation/verification checkpoint: **2026-10-03 21:29:20 +01:00**, Europe/London. Status: **implemented control/client slice; GUI-1a remains in progress**. No additional stage-completion timestamp.

## Changes implemented

- Added typed owner-local lifecycle/shutdown contracts, registration and two exported schemas.
- Added separate ephemeral desktop-launch authority, consumed before child/model/provider startup, absent from settings/projections/argv/logs. Requires owner API authentication plus exact Core epoch/session/request identity; external/remote/unowned shutdown rejected.
- Added ACK-after-drain completion hook and shutdown effect-admission fence; exact nonce retry supported without claiming process exit.
- CLI now awaits owned shutdown through normal cleanup; ordinary serving remains compatible. Runtime startup moved under its cleanup guard.
- Added desktop exact-child launch authority and bounded lifecycle client, non-transferable epoch/session binding, safe attached refusal, correlated retries and no force-kill/descriptor adoption.
- Added 17 Python test instances (including actual isolated deterministic CLI exit), four C# ownership tests, and updated the existing ordinary CLI migration test double/assertion.
- Updated roadmap to v1.7, ownership specification and opt-in runbook; added separate detailed verification. No managed launcher/host integration or ordinary default change is claimed.

## Verification

Final dedicated full gate: **703 Python passed /25 skipped**, **8 PWA passed**, mypy **262 files**, Ruff/schema/compileall passed. Final **84 C# passed**, shell/full-app/widget builds **zero warnings/errors**. Actual isolated owned CLI received matching ACK, exited **0** and left no reachable listener. C# synthetic children exited normally via stdin; no force cleanup on passing runs.

Initial full gate failed one old test-double signature; final gate passed after updating it to assert ordinary launches remain unowned. Early lint/analyzer issues were repaired before final gates. Detailed environment, command, fixture/live-process and acceptance boundaries are in the linked report.

Owner Core PID 52000/start time preserved; no owner settings/data, reference originals, overview or other contributor logs edited. No UI/model/voice/provider/renderer acceptance is inferred. GUI-1a/full goal remain active/open. Next is actual profile discovery/startup/recovery/owned-exit coordination in ShellHost and opt-in launcher integration.

Final documentation/preservation check: **2026-10-03 21:32:46 +01:00**. All local links in the five updated/new documents resolve; the same three baseline/specification scopes remain checked; five reference byte sizes/SHA-256 match; overview diff is empty; no QA SoraShell/Windows PowerShell child remains and owner Core PID/start time are unchanged.

[Verification](../docs/verification/GUI1_LIFECYCLE_CONTROL_GPT-6.1-Sol_2026-10-03.md) · [Roadmap](../SORA_GUI_IMPLEMENTATION_ROADMAP.md).
