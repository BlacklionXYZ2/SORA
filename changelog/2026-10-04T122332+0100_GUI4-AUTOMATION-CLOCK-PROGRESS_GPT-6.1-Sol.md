# GUI-4 Automations schema and time foundation progress

Model name: **GPT-6.1 Sol**. Source checkpoint: **2026-10-04 12:23:32 +01:00**, Europe/London. Status: **GUI-4a/c in progress**, not a stage-completion date or active scheduler delivery.

## Implemented changes

- Added four closed exported Automation spec/definition/slot/occurrence contracts with bounded typed triggers/behavior/policies, aware IANA timezone timestamps, versions and actual task/run-link invariants. Configuration/reservation cannot claim completed execution.
- Added pure one-off/daily/weekly/fixed-interval calculations with anchored UTC elapsed intervals, first-fold-only autumn behavior and skipped nonexistent local times. Gap bookkeeping uses the first valid transition instant so whole-day skips do not hide a subsequent legitimate occurrence. Added bounded missed/catch-up/grace/overlap decisions; no automatic retries/backlog executor.
- Added29 focused tests covering calendar/elapsed/restart-serialization/boundary/DST/invalid-input/evidence cases. Added first-party timezone dependency and locked2026.5 data in the isolated environment after observing missing IANA data on Windows. No owner environment update.
- Inspected the original Automations reference; recorded the full persistence/admission/worker/recovery/API/shared-UI contract and outstanding scope, not a reduced substitute for that interface. Added verification document and roadmap progress with prior history intact.

## Verification and limitations

[Verification](../docs/verification/GUI4_AUTOMATION_CLOCK_GPT-6.1-Sol_2026-10-04.md):29 focused passes, targeted lint/type/schema checks; full isolated exec41461 terminal result is recorded only once observed. No migration/table/API/worker/scheduled task or native UI is delivered by these foundations. No owner restart/reload/settings/data/device/provider operation, default client change or denied native retry. Existing completion timestamps/contributor logs and original references preserved. Full goal active; next implement the canonical persistence/receipts/reservations and actual admission/recovery under the contract.

Final regression observed **2026-10-04 12:26:25 +01:00**, exec41461 terminal exit0: **840 Python passed /25 opt-in skipped in96.42s; 8 PWA passed; mypy280/lint/schema/compile passed**. No later source/test/lock/schema changes. Roadmap nowv1.29; all completed dates and earlier evidence remain unchanged.

Documentation checkpoint **2026-10-04 12:30:28 +01:00:**145 local links across roadmap/contract/report/log, zero broken; five original assets match manifest size/SHA-256, exactly the three original completed-stage checkboxes retained. Tracked Git whitespace check exit0; untracked documents are not falsely claimed covered by that tracked check. Full goal status re-read as active; no completion/blocked/pause update.
