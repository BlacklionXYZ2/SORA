# GUI-3a canonical Memory browser verification

Model name: **GPT-6.1 Sol**. Implementation checkpoint: **2026-10-04 08:37:17 +01:00**, Europe/London. Status: **implemented source slice / GUI-3a in progress**. No GUI stage-completion timestamp.

## Implemented scope

The [finalized contract](../gui/GUI3_MEMORY_BROWSER_CONTRACT_GPT-6.1-Sol_2026-10-04.md) describes owner-local bounded canonical list/detail/literal-search service, signed filter/scope/limit/instance cursors, explicit SQL read snapshots, live states/counts, exact microsecond-aware expiry, no deleted/foreign record fallback, actual supported metadata and private-capture exclusion. It reuses existing storage, global revision and content registrations. Two schemas exported; no storage migration/AppSettings version/default changes. No memory mutation or model tool is inferred from browsing.

The shared-host Memory window has Overview/Search/state/project/scope filters,50-row pages, bounded Previous/Next history, exact-ID inspection, inert owner content/provenance, registered evidence list and guarded navigation. Tray/menu/Chat More/Settings/IPC/direct/root/full launch selection and UI-only placement are connected. One existing client/session; no panel timer, independent synchronizer/store/provider. Read/selection/query/epoch fences and explicit stale/unknown labels retain process-local cache/drafts without replay. Close hides; accepted Quit cancels reads; pending navigation protects Quit. Graph is unavailable, not a fixture graph. Correction/forget and semantic acknowledgement remain GUI-3b/c.

## Fresh checks

| Check | Result |
|---|---|
| Focused `pytest tests/api/test_memory_browser.py -q` | **26 passed in2.60s** |
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **309 passed**, zero failed/skipped |
| Shell/Desktop/Widget final builds | all three zero warnings/errors |
| `./scripts/verify-shell-launchers.ps1` | effect-free actual full-launcher forwarding includes Memory; passes |
| `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` | **745 Python passed /25 opt-in skipped in89.12s**, **8 PWA passed**; mypy270/lint/schema/compile pass; exec4325 terminal exit0 |

Earlier pre-expiry-refinement full run completed **744 Python passed /25 opt-in skipped in89.95s**, **8 PWA passed**, mypy270/lint/schema/compile; exec20479 terminal exit0. The final run above includes the later precise-expiry correction and parity case. No owner `.venv` is used for verification. Final regression was observed terminal at **2026-10-04 08:40:35 +01:00**, not restarted after an observation gap.

HTTP fixtures exercise actual ephemeral loopback production API/runtime/SQLite with synthetic temporary records, not a live owner profile or paid provider. Coverage: empty pages, owner/global/current-project isolation, exact unknown/deleted/foreign IDs, literal `%`/`_`/backslash/quoted searches, exact scope, bounded long/large content, versions, expiry/timezone/microsecond parity with canonical repository, supersession without redirection, deleted successor withholding, later-admission ceilings/live deletion/counts, signed filter/owner/project/epoch/key/tamper rejection, closed/duplicate/oversized/control queries, method/remote/Core-header rejection, registered owner/device/project-only evidence and exclusion of both raw private capture IDs and registered capture-directory files, and redacted invalid-record errors. No private capture file content is returned.

C# cases copy only public fields, reject target/owner/project/epoch/filter/duplicate/oversized/private shapes, render owner HTML-like text inertly without raw private properties, preserve explicit successor identity, validate route encoding/cursors, fence late query/selection/epoch responses, retain stale cache without reconnect freshness, and exercise shared API reads while the model is down without mutation/Chat-draft loss. The replacement-Core test asserts a genuine pending read before changing epoch; it is not a preexisting-disconnect false positive. Memory command and UI-only placement validation are covered. Source builds cover the native form; pure/component tests do not demonstrate its actual layout or focus behavior.

## Environment, preservation and limits

Owner Core **PID52000**, original start **2026-09-29T21:49:32.7934609+01:00**, remained running from its existing `.venv` when checked at08:28:46 and again at **08:42:54 +01:00**. No owner settings/memory/model edit/restart/reload, physical device/desktop probe, provider dispatch or paid inference. No new native GUI launch or equivalent retry of the earlier policy-denied launch/setup workflow. All **9 original reference/overview/earlier-draft artifacts** retain byte sizes/SHA-256. No reset/commit/material deletion.

Documentation read-back at **2026-10-04 08:44:33 +01:00**: **141 local links, zero broken** across the six changed/new delivery documents. Exactly GUI-0a/0c/0d remain checked at **2026-10-03 19:24:55 +01:00**. `git diff --check` passes with existing line-ending warnings; untracked files are also built/tested/read back, not assumed validated by Git alone. The994-file pre-reconciliation fingerprint has only19 declared existing-file changes across that documentation update and this Memory slice; **975 other pre-existing files** remain byte-identical. New Memory service/tests/forms/schemas/docs/logs are separate additions; previous model logs and source/reference baselines are preserved. This validation time is not a GUI-stage completion time.

Actual native Overview/Search/row/ID/paging/evidence-open/hide/reopen/resize/placement/keyboard/IME/screen-reader/high-contrast/text/DPI/large-data operation and latency remain open. The supplied Memory concept was visually inspected, but that is not a screenshot of the new form. Current source supplies native controls, stacked narrow layout, bounded status with accessible/tooltips and shared preference/theme handling; no physical acceptance is claimed. Registered navigation is revalidated but not an atomic memory-and-file transaction. Cached pages are explicit reads, not continuously polled canonical truth.

GUI-3a stays in progress and GUI-3 overall remains open for GUI-3b version-checked correction/forget and GUI-3c acknowledged conversation-to-memory presentation. GUI-4 scheduler, GUI-5 real relationships/final visual design and GUI-6 ordinary-launch/release acceptance remain required, with all earlier host/Chat/retained-workflow/Voice/Settings/native/live/physical gates retained. Next safe source task is GUI-3b; no goal completion is inferred from a green suite.
