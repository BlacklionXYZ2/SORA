# P06 P05-dependency closure changelog

- Stage: P06 — Antigravity and rule-based routing
- Model name: GPT-5.6 Sol
- Dependency closed / combined stage acceptance: 2026-09-08 15:17:15 +01:00 (Europe/London)
- Original P06 implementation model: Gemini 3.8 Flash
- Original implementation timestamp: 2026-09-08 13:55:00 +01:00 (Europe/London)
- Status: complete

## Integration changes

- Preserved Gemini's Antigravity adapter, deterministic routing, fast paths, privacy filtering,
  bounded fallback, conversational steering, and adaptive presentation.
- Replaced the temporary coding-write hold with a verified P05 handoff: configured writes select
  Codex with no fallback, allocate an explicit-base worktree per run, bind the provider and request
  to the same live lease, capture the review artifact, and release the lease on every terminal path.
- Kept the fail-closed behavior for unconfigured isolation and explicit unavailable providers.
- Expanded edit/change intent classification after live acceptance found a direct editing prompt had
  been classified as a read-only coding request.

## Acceptance evidence

- A real P06-routed GPT-5.6 Luna task used full-SORA base
  `f370082b89924da37b832fec59b78e1ab4b9b52c`, changed only the two requested files in its owned
  worktree, persisted native-session and review evidence, left the source checkout clean, and
  released all leases.
- Host verification against the exact live worktree passed all 6 Codex provider tests.
- The integrated repository passed 145 tests, Ruff, strict mypy across 85 source files, source/wheel
  builds, and isolated-wheel imports across P05/P06 components.

This is a dependency-closure and integration record, not a reassignment of Gemini 3.8 Flash's P06
implementation credit. Gemini's original changelog remains authoritative for the P06 feature work.
