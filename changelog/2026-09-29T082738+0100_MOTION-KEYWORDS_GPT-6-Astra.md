# Small-model avatar motion keywords

- Attribution: **GPT-6 Astra**, as requested by the owner.
- Completed: **2026-09-29 08:27:38 BST (UTC+01:00)**.
- Status: **keyword prototype implemented and verified**; parameterised movement and autonomous
  perception remain separate future work.

## Changes

- Added `src/sora/contracts/motion.py` and exported `motion-choice.schema.json`: one required keyword
  and no arbitrary parameters or authority fields.
- Added optional `MotionDialogueProvider` protocol and constrained JSON selection to the configured
  dialogue provider. Small-model classification receives only current owner text and fixed guidance.
- Connected validated model choices to grant-backed `LocalAvatarSession.present` in text dialogue;
  explicit remote denial, file/image exclusion, none fallback and dispatch-only acknowledgement.
- Added a trusted description for ordinary capability questions so SORA can explain the new keywords.
- Preserved explicit poses across automatic thinking/waiting transitions rather than overwriting
  them with idle immediately after a chat request.
- Added 17 deterministic cases plus an opt-in real-model/real-Unity test, a user guide, verification
  record and additive roadmap note. Existing user changes and old attribution remain intact.

## Evidence

- Final repository gate: **405 Python passed / 13 opt-in skipped**, **7 PWA passed**, Ruff, strict
  mypy across 201 source files, schema freshness and compileall clean.
- Live installed Gemma 4 E2B: **11/11 keyword probes correct**, all **5/5 chat-to-real-Unity pose
  states** observed, and the normal model response listed available keywords. Final test 56.04 s.
- Failed/unknown JSON, remote/file-context triggering and revoked dispatch tested. Test-owned
  avatar/model resources were closed; no normal owner profile or paid specialist was used.
- No claim of rendered animation quality, command-correlated completion, voice support, arbitrary
  movement or autonomous desktop/window/file discovery.

Guide: `docs/runbooks/SORA_MOTION_KEYWORDS.md`.
Evidence: `docs/verification/MOTION_KEYWORDS_GPT-6-Astra_2026-09-29.md`.
