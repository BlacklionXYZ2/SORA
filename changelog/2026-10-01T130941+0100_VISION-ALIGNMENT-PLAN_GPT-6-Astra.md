# Vision alignment plan — owner clarification incorporated

Model: **GPT-6 Astra**  
Planning completed: **2026-10-01 13:09:41 +01:00 (Europe/London)**  
Status: **Planning complete; no runtime implementation performed.**

## Changes

- Developed [VISION-ALIGNMENT_2026-10-01.md](../docs/plans/VISION-ALIGNMENT_2026-10-01.md) around the owner's confirmed product direction: static GUI/JSON access for SORA, no local permission applications, general desktop interaction and readable local files at will.
- Specified a real local-policy replacement for the grant/approval lifecycle, not ephemeral grants or hidden self-approval. Remote authorization remains separate.
- Made direct user-file authoring off by default and delegated to capable agents; distinguished it from ordinary desktop interaction and Core's own memory/settings/task persistence.
- Evolved the deliberate one-key prototype into a typed companion-call proposal with read, target, payload, effect and delegation semantics; staged broader controls and visual-only interaction explicitly.
- Reconciled native perception, file search, provider/path coordination, GUI truth, startup and voice integration; added acceptance gates and corrected dependency order.
- Corrected source baselines: full-helper launcher, walking/screen/memory hooks, existing agent-authored changelog services and Codex direct-root support already exist and must be reused.
- Preserved DeepSeek's complete original proposal in [the archive](../docs/plans/archive/VISION-ALIGNMENT_2026-10-01_DEEPSEEK-ORIGINAL.md).
- Added precedence/integration notes to the earlier native-perception and memory/agent plans; added a planning-only pointer to SORA_IMPLEMENTATION_PLAN.md without changing historical completion gates.

## Verification

- Read current authorization contracts/rechecks, settings, launchers, dialogue hooks, local-file reader, direct-root adapter support and relevant planning documents. DeepSeek's live GUI observations remain attributed; they were not rerun.
- Checked the revised plan's three local links: all exist.
- Parsed all 14 JSON call examples successfully; all 10 delivery rows remain marked Planned.
- Compared the archived original to the pre-edit document after newline normalization: identical.
- Roadmap git diff whitespace check passed (Git emitted its existing LF/CRLF normalization warning).
- The first documentation check expected 15 examples instead of the actual 14; corrected the check and reran successfully. This was a check-count error, not a malformed example.

No application code, active settings, model configuration or running processes were changed. No app/model/native test suite was run for this documentation-only task. The source baseline overview and other contributors' attribution remain intact.
