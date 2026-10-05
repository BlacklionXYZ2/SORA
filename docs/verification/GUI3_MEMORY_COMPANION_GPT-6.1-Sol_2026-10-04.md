# GUI-3c chooser, retrieval and Chat verification

Model name: **GPT-6.1 Sol**. Source checkpoint: **2026-10-04 10:45:52 +01:00**, Europe/London. Status: **implemented source/component slice; GUI-3c in progress**, not native/live acceptance. [Contract](../gui/GUI3_MEMORY_COMPANION_CONTRACT_GPT-6.1-Sol_2026-10-04.md).

## Observed results

- Focused Python: **104 passed in9.95s**, combining23 deterministic companion cases, existing compact-call/native-presentation cases and23 transport cases. The companion fixture uses production authenticated dialogue HTTP/SQLite with a deterministic chooser and fake registered host; it does not inspect Windows or call a real model.
- Final C#: **369 passed**, zero failed/skipped, including20 new Memory activity/parser/sync/session/pending cases. All three Windows client builds passed with zero warnings/errors. Effect-free real-launcher forwarding passed. Observed **2026-10-04 10:45:28 +01:00**.
- Isolated full regression runs through `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1`, live exec session92619. Lint/mypy277 passed and836 tests were collected. Final terminal result is appended only after that same process completes; startup/progress is not a passing result.

Python coverage: old memory lookup across a context limit, scoped literal paging, secret/foreign-project exclusion, issued/unexposed/expired/cross-turn/cursor-bound references and64-target cap; observation-budget trimming and exact content-free deduplicated retrieval metadata; pending response waits for ACK, positive/negative outcomes, ID/dialogue correlation; absent host, invented target and changed version; Stop prevents a cancelled request becoming late success; quoted/negative/hypothetical prompts cannot expose presentation; extra authority/raw-ID/path fields rejected; redacted projection/SQLite errors and corrupted canonical context after selection do not leak or substitute another record.

C# coverage: typed retrieval versus positive/negative host labels, private-field withholding, malformed source/stage/ID/version/generation and oversized arrays; no pending/dispatch/unknown success chips; sync dedup/latest64/offline cache/resync/new-Core clearing; model-down guarded owner chip request carries exact ID/version/epoch, preserves Chat draft and reports only requested; pre-selection pending check rejects cancellation/target/epoch mismatch. Pure tests do not execute the native `MemoryForm` or render/interact with chips.

Initial verification found a C# fixture method-name error, overly small test context budget, actual canonical context corruption during a post-selection rebuild, and type-checking issues. These were fixed before the recorded passing checks. No earlier failing result is labelled passing.

## Owner and environment boundaries

Owner Core PID52000/start **2026-09-29 21:49:32**, `.venv/Scripts/sora.exe`, rechecked unchanged at **2026-10-04 10:45:52 +01:00**. Tests use the isolated environment/temp databases, not that `.venv` or owner state. No owner restart/reload/migration/settings edit, microphone/avatar operation, paid provider call or new native action; no equivalent retry of the earlier denied native workflow. An already running Core does not gain source changes without a later normal restart.

AppSettingsv9, UIpreferencesv1, migration11 and default Desktop remain unchanged. Existing transport/management evidence and contributor logs remain separately dated. Host ACK is a host report, not OS attestation; retrieval selection is not proof of model thoughts or consumption. Native/live/physical acceptance and all preceding roadmap gaps remain open, alongside the persisted scheduler, real graph/design and ordinary-launch/release work. Full goal remains active.

## Final regression

**2026-10-04 10:48:09 +01:00:** Same exec session92619 returned terminal exit0. Final-source `./scripts/verify.ps1`: **811 Python passed /25 opt-in skipped in96.80s; 8 PWA passed; mypy277/lint/schema check/compile passed**. Source/contracts/tests unchanged afterward; subsequent documentation only. This completes the component regression, not native/live acceptance or the full goal.
