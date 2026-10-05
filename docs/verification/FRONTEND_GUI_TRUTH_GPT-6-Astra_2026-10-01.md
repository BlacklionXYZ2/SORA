# Frontend goal: first GUI truth repairs

Verified: **2026-10-01 14:38:11 +01:00 (Europe/London)**. Model: **GPT-6 Astra**.
Scope: W6a progress; **not completion of the frontend goal or the full W6a acceptance matrix**.

## Implemented

- Shared runtime conversation projection replaces the hardcoded talking state. Both companion endpoints now expose idle/thinking/model availability consistently. The avatar pose is a separate renderer_state; the full-app avatar page consumes that field with an older-server fallback.
- Actual dialogue model label is shown separately from available specialist harnesses in the widget, and in the full-app status header. Volatile polling refreshes this without requiring a durable message event.
- Shared inert Markdown-to-readable-text rendering for assistant messages: headings, bullets, emphasis, links and fenced/inline code. Owner messages remain literal. This is a small supported subset, not full CommonMark or a web renderer.
- Full-app Send clears its submitted composer before awaiting, preserves a new draft, restores a failed draft only when the composer is empty, and disables duplicate chat action buttons during work. Widget Send also preserves new composer text. Other action/attachment-draft races still need broader acceptance.
- Footer reports response received then returns to current status rather than permanently showing Sent to SORA.
- Increased full-app attachment row/widget composer space; reference label sizes to text; keyboard hint changes between expand/compact and has a separate full-width footer.

## User-side evidence

Computer Use inspected the owner's existing full app: raw assistant Markdown and stale footer reproduced. No owner chat/test message was added; no owner runtime was restarted.

Built isolated clients under .local/frontend-qa-20261001 and ran a separate real Core on port 18783 using the deterministic offline dialogue fixture. Through the rebuilt GUI, entered and submitted a benign multiline Markdown test. Verified:

- User message retains its literal Markdown; assistant response shows readable heading/bullets without raw emphasis delimiters.
- Submitted composer clears; disabled action buttons and Working state appear during submission, followed by response/status.
- Full app and widget show Offline test model, not a specialist's name.
- Widget sees the same conversation; compact/expanded rendering works.
- Expanded Reference ID label no longer overlaps the input.
- Expansion hint changes, and final full-width footer was visually checked in both compact and expanded modes.
- Full-app Attach file button is visible at the tested size.

These are actual rendered desktop-client checks against an offline fixture, **not** proof of live LLM tools, agent model selection, vision, microphone, general desktop effects or animation quality. The long-running draft race was repaired in source but not reproduced with a deliberately delayed live response. Mixed-DPI/100%/150% complete matrix remains open. Final widget layout was rechecked after the last layout change; the last full-app change was header ellipsis only and rebuilt successfully.

## Automated evidence

- scripts/verify.ps1: **471 passed / 13 explicit opt-in skips**, 74.62 seconds; Ruff, mypy across 214 files, generated schema freshness, compileall and **7 browser tests** passed.
- Three existing provider-test typing errors initially blocked mypy; corrected Path arguments to the declared string interface and annotated ScreenViewKeyword. No provider behavior changed in that repair.
- Final C# suite: **36 passed** (including new transcript/status tests).
- Final targeted API/settings: **5 passed**; added assertions for endpoint state agreement during idle/thinking, disconnected renderer distinction and model label.
- Both final Windows client builds: **zero warnings/errors**.
- Full Python gate preceded the final two C#-only layout tweaks; final client builds/C# suite and targeted API tests followed them.

## Operational notes and remaining work

The owner application's currently running old binary was not hot-replaced. Normal startup rebuilds the source; isolated QA artifacts remain for reproducibility. A combined shell setup command was rejected before execution, so the benign test was entered through the actual GUI instead. Hidden QA client startup was not targetable; only owned QA clients were restarted visibly for interactive inspection.

See [full goal tracker](FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md). Static access replacement, complete agent/model catalogue and delegation, passive/native perception, broader actions, voice, avatar controls, path ledger and complete frontend acceptance remain open.

After verification, stopped only the exact observed QA uv/Python/client processes after checking their command lines against the isolated profile. Fresh inventory returned **zero remaining owned QA processes**. QA data/logs remain; owner processes were not selected for cleanup.
