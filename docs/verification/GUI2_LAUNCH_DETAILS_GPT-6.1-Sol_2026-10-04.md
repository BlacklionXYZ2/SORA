# GUI-2 read-only launch details and modal draft guards

Model name: **GPT-6.1 Sol**. Implementation/verification checkpoint: **2026-10-04 07:51:34 +01:00**, Europe/London. Status: **implemented slice / GUI-2 in progress**. No stage-completion timestamp.

## Read-only command provenance

The canonical Settings projection adds optional `launch_details` version1 metadata, not stored settings. AppSettings stays v9, all84 editable fields/defaults/effect tiers and the UI-only v1 store remain unchanged. No new route/permission/poller/model client/store or arbitrary launch editor.

Advanced Settings displays three inert argument arrays with explicit provenance:

- **Core-captured submitted managed-worker arguments:** captured alongside the worker configuration submission. Only exposed for an owned managed wrapper still reported live with a capture. This is Core submission evidence, not independently read OS/process arguments or measured GPU/model capability. It is not rebuilt from subsequently replaced server configuration. Close clears the capture; failed/stopped/missing/fake-without-capture/non-managed workers are unavailable.
- **Next model reload preview:** uses saved model-tier preferences blended with current effective boot settings, through the same candidate helper used for real reload admission. Saved executable/port/backend boot changes do not silently apply during model reload.
- **Next Core start preview:** uses saved preferences, including boot-only changes, and is inapplicable for saved non-managed backends. Neither preview probes files/runtime, starts a helper, validates model compatibility or implies it has loaded. Missing model/projector/draft paths or unprintable/unbounded tokens yield unavailable text.

Launch and preview use the same typed argument builder, preserving exact explicit `--mmproj`, loopback bind, alias, no-webui and supported context/cache/GPU/flash/batch/speculation parameters. Authentication remains environment-only. Projection and display do not serialize environment, API keys, raw logs or provider prompts. Core and the pure C# presenter validate bounded printable argument grammar, required fixed flags/bind, duplicates/unknown flags and credentials. Unexpected metadata is withheld, not executed or printed indiscriminately. Arguments are JSON-escaped readable arrays; they are not shell commands/clickable actions. Unknown private payload properties are ignored.

The compatibility Desktop editor now receives actual snapshot connectivity for current/stale labels. Older Core versions without launch metadata report unavailable; stale cached arrays are explicitly labelled last-known/unconfirmed. Shared host remains the only owner of its refresh/API/effect slot. Ordinary Desktop default is unchanged.

## Settings race corrections

Source review found a modal-editor timing gap: a retained old-Core draft could miss observation of an equal-revision replacement until the Save response. `BeginSave(currentEpoch)` now refuses that submission before the API call. Dirty changes and model-purpose close observe the latest cached revision/epoch immediately. A component case verifies the refusal retains the draft, leaves Busy false and allows only the original epoch.

File/folder pickers hold the editor's modal-work count so a background Settings refresh cannot dispose/replace the edited controls under the dialog. Selection becomes an unsaved draft; cancel/close/new-Core outcomes retain it and discovery is not sent to a changed Core. Read-only inspections and Save/refresh/discard/reload consequence dialogs also count as pending modal work, protecting host Quit. Multiple-projector cancellation no longer announces a projector was selected; changed-Core choices are rejected. Noneditable path controls disable browse as well as text editing.

These are source/component corrections, not actual mouse/keyboard/modal/hide/Quit acceptance. Native behavior remains an open gate.

## Fresh evidence

| Check | Result |
|---|---|
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **284 passed**, zero failed/skipped/warnings |
| `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` | **719 Python passed /25 opt-in skipped in87.52s**, **8 PWA passed**; mypy267/lint/generated schema/compile pass; exec82861 terminal exit0 |
| Targeted managed llama/AppSettings | **29 passed /2 real-model opt-in skipped**, mypy four selected sources pass |
| Shell/Desktop/Widget builds | all three zero warnings/errors |
| `./scripts/verify-shell-launchers.ps1` | effect-free actual-full-launcher defaults/selection/retained-panel/unsupported-effort checks pass |
| `git diff --check` | pass; pre-existing line-ending warnings only; new source separately compiled/tested |

New Python cases cover one launch/preview builder, missing/no-I/O model/draft previews, capture retention after configuration replacement and cleanup, secret exclusion, grammar/size/control/duplicate/bind rejection, active/reload/next-start separation and exited/no-capture states. Factory/process/HTTP behavior is mocked; these cases do not prove real llama.cpp loading or native user input. C# cases cover safe read-only/current/stale/old-Core/missing/unavailable formatting, private-field exclusion, malformed/credential/duplicate/control/oversized/unknown/bind rejection and pre-submission draft-epoch refusal.

Owner Core **PID52000**, original start **2026-09-29T21:49:32.7934609+01:00**, remained running from the owner's existing `.venv`. No owner model load/reload, settings edit/restart, physical audio/desktop probe or new native GUI launch. No equivalent retry of the earlier policy-denied native-launch workflow. Reference/overview/earlier-plan originals and completed-stage records preserved; no reset/commit/material deletion.

## Remaining goal scope

GUI-2 native category/disclosure/argument-view/purpose/path/reconciliation/keyboard/DPI/high-contrast/hide/Quit/device/default-persistence/restart and actual model reload/error/last-good recovery/provider-entitlement gates remain open. Earlier GUI-0b/GUI-1 acceptance still required. Next available code work is GUI-3a canonical Memory service/browser under its recorded GUI-0 contract dependency; GUI-3b/c, GUI-4 scheduler, GUI-5 graph/final visual design and GUI-6 ordinary launch/release acceptance remain required. This slice does not close the GUI objective.
