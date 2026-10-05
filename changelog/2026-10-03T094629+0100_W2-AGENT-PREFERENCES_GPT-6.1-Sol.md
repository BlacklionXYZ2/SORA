# W2 agent preferences — GPT-6.1 Sol

Completed slice: **2026-10-03 09:46:29 +01:00**, Europe/London.
Contributor/model-name attribution: **GPT-6.1 Sol**
Status: implemented and verified preference slice; overall frontend goal/W2/W3 still in progress.

## Changes implemented

- Added `runtime/agent_preferences.py`: strict typed per-agent enable, purpose, exact preferred
  model, supported preferred effort and model purpose; Hermes effort/Antigravity tier validation.
- Updated unified AppSettings/SettingsEdit/projection to v7, additive legacy migrations/backups,
  complete v7 preferences, bounded writes, live effects and delegation-epoch invalidation.
- Updated AgentCatalogue with canonical preferences/enable state/effective defaults without
  altering discovered metadata or asserting model access.
- Pinned owner-local preferences for new/board tasks in canonical persistence; explicit overrides
  remain independent. Added disabled admission/retry/steering and launch checks. No fallback changes
  to a requested model, no mutation of provider files or queued/retry pins.
- Added shared-client catalogue preference details/disabled action state and full-app agent Settings
  model dropdown/refresh. Preserved drafts/choice lists through Save; named discovery failures.
  Windows projections accept v7. Updated example/runbook and isolated QA settings-controller wiring.
- Added 10 preference tests and adjusted existing current-version assertions; preserved prior
  roadmap/model attribution and all unrelated dirty-tree work. No commits or owner-Core restart.

## Verification

- Final standard gate: **603 Python passed /24 opt-in skipped**, **8 PWA**; Ruff, mypy243,
  contracts and compileall passed. **41 C#**; both Windows builds zero warnings/errors.
- Computer Use: actual Settings metadata dropdown, GUI low-tier model/purpose Save, exact disk
  values, forced owned-Core restart and restored GUI values, final choices-after-Save review.
- Native catalogue counts **7 Codex /22 Hermes /18 Antigravity**, metadata only; no live inference
  or independently verified entitlement. Fixture tests cover pinned model delivery and revocation.
- QA tree/GUI closed, port released; owner Core PID52000 untouched. Forced QA cleanup is not
  graceful restart evidence. No Unity or physical audio acceptance in this slice.

Detailed evidence and remaining gates:
[W2 agent preferences](../docs/verification/W2_AGENT_PREFERENCES_GPT-6-Astra_2026-10-03.md).
Next: real project selection/write leases and a compact multi-model-purpose/delegation schema,
then full user-side action/voice/avatar/memory acceptance. The overall goal is not complete.
