# Independent audit of Gemini 3.8 Flash's P03A and P06, with one steering fix

Model name: **Opus 5.5**. Checkpoint **2026-10-05 18:40:44 +01:00**, Europe/London. Status:
**audit complete; one fix applied; two privacy gaps open pending an owner decision.** No
checkbox, completion timestamp or earlier contributor's record was changed.

## Changes

- `src/sora/routing/router.py` `disambiguate_steering`: an instruction that names more than
  one specialist ("cancel the Hermes task, not Codex") now returns no target instead of
  whichever name was checked first. Voice cancel/steer then asks which task is meant. Single-name
  and pronoun behaviour is unchanged.
- `src/sora/providers/antigravity.py`: corrected the class docstring, which falsely said in-place
  writes were disabled. This is a comment-only change; behaviour is unchanged.
- New `tests/verification/test_gemini_p03a_p06_audit.py`: 4 tests for criteria that hold or were
  fixed, plus 6 `xfail(strict=True)` tests pinning confirmed gaps.
- New record `docs/verification/P03A_P06_INDEPENDENT_AUDIT_Opus-5.5_2026-10-05.md`. Updated the
  ledger rows in `docs/verification/README.md`, added audit notes under P03A and P06 in
  `SORA_IMPLEMENTATION_PLAN.md`, and updated the rerun line in the roadmap's §4.0.

## Verification

- Audit tests: 4 passed, 6 strict xfailed. With `--runxfail`, each of the 6 fails with its
  stated assertion.
- Full gate after the change: `ruff check` clean; `mypy` strict clean (286 files);
  `export-contracts.py --check` passed; `pytest` **908 passed / 25 opt-in skipped / 6 xfailed**
  in 125 s; `compileall` OK. Component evidence only.
- Same session, before the change: `dotnet test` 369/369; desktop_shell, desktop_app and
  desktop_widget built with 0 warnings and 0 errors; PWA 8/8.
- Not run: live Antigravity/Hermes/Codex, native desktop, hardware.

## Limits and next

- **Open, live (P06.2):** local-only editor/reference/API tasks can route to Antigravity or Hermes,
  because the router counts only Codex as cloud.
- **Open, latent (P06.3):** the fallback re-route drops the local-only flag. Fix it together with
  P06.2.
- Both need the owner to decide whether private context may go to hosted specialists.
- Latent, no production caller: `dispatch_capability` lacks execution-time rechecks, the social
  module never reaches context, and `present_result` misattributes patch-less results.
