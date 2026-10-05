# GUI and LLM-to-avatar review

- Attribution: **GPT-6 Astra**, using the owner's requested changelog name.
- Completed: **2026-09-29 08:07:52 BST (UTC+01:00)**.
- Status: **review completed; findings open; no application-source implementation**.

## Changes

- Added `docs/verification/GUI_AND_LLM_AVATAR_REVIEW_GPT-6-Astra_2026-09-29.md`
  with live test outcomes, exact chat probes, code-supported causes, prioritised GUI improvements,
  acceptance criteria and explicit visual-verification limits.
- Retained one QA board note and three avatar-control chat tests in the isolated
  `.local/settings-qa-20260928` profile. No specialist task was started.
- Stopped QA-scoped Core and desktop/widget clients after testing; fresh process inspection found
  no remaining QA-scoped processes. Normal owner profile and unrelated model servers were preserved.

## Results

- Five manual pose buttons reached the renderer's reported state.
- Natural-language Wave, Sit and Move did not execute; the direct-dialogue path lacks an avatar
  action interface. Runtime-driven thinking/idle is working, but is not model-authored motion.
- Board expansion, note creation and Hermes assignment/colour worked. Drag/drop did not move the
  note; Activity exposes execution backend as unassigned despite the board assignment.
- Recorded clipping/density, progress feedback, technical terminology, model/provider labelling
  and avatar-recovery improvements. Attachment picker open/cancel and widget conversation sync checked.
- Rendered avatar animation quality remains unverified because the transparent overlay was not
  exposed as a targetable Computer Use window. Unreliable captures after the overnight pause were
  excluded from product-defect evidence. No new regression-suite pass is claimed.
