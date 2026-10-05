# SORA implementation-plan update — motion keywords

Recorded: **2026-09-29 08:27:38 BST**. Attribution: **GPT-6 Astra**.

Owner-directed follow-on: start with model-selected animation keywords before parameterising motion.
The canonical roadmap receives an additive status note; no prior stages are renumbered or retroactively
closed, and `SORA_OVERVIEW.md` remains unchanged.

Implemented: one-field keyword contract, constrained small-model selection, validated owner-local
dispatch to existing poses, remote/file-context exclusion, and pose retention across busy states.
Live Gemma 4 E2B + packaged Unity passed all five pose paths; 11 keyword probes passed. The final
repository gate passed 405 tests with 13 opt-in skips, plus 7 PWA checks.

Open next steps: owner visual acceptance, command-correlated completion feedback, parameterisation
as a separate extension, and an independently bounded read-only desktop/window/file tool loop.
Those perception paths are not made autonomous by this motion implementation.

See [verification](../../../docs/verification/MOTION_KEYWORDS_GPT-6-Astra_2026-09-29.md) and
[user guide](../../../docs/runbooks/SORA_MOTION_KEYWORDS.md).
