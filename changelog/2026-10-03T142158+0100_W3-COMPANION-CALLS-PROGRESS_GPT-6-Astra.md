# W3 companion calls and delegation — GPT-6 Astra

Implementation/verification checkpoint: **2026-10-03 14:21:58 +01:00**, Europe/London.
Status: **implemented progress slice**, not W3/W2/frontend completion. GUI and real-model
acceptance remain open. Concurrent contributors' changes and attribution were preserved.

## Changes implemented

- Added the strict discriminated `CompanionCall` contract, reusing the existing window/file read
  variants and adding `list_agents`, `delegate`, keyword `pose` and pointer-only `move`. Core
  assigns version/call IDs; model-authored authority, commands and coordinates remain rejected.
  Constrained output contains only currently enabled/implemented alternatives and definitions.
- Added a unified local chooser to the existing dialogue provider and bounded turn loop. Legacy
  read-only providers remain supported. One terminal effect is selected after up to six bounded
  discovery/read steps; malformed output gets one bounded repair, not prose-to-action guessing.
  Unified `finish` cannot fall through to a second independent motion selector.
- Added turn-local specialist/model/project references over the existing cached catalogue and
  canonical preferences. Discovery is paged; references must be known, and model references must
  have been exposed. Disabled agents are omitted. No automatic metadata refresh, inference,
  entitlement claim, invented model ID or silent specialist fallback is added.
- Routed `delegate` through existing Core task admission, provider selection, project validation,
  policy epoch, queue and durable receipt. The original owner's request remains provider intent.
  SORA's bounded suggested brief is separately stored, not an instruction/permission upgrade.
  Explicit recognized owner harness selection cannot be overridden by the suggestion.
- Guarded admission inside the database transaction against cancellation/deadline/policy changes.
  Shielded admission is retained/observed on caller cancellation. A receipt means queued, not
  completed, and shows the selected model, project and mode.
- Companion-delegated agent context does not automatically include the previous desktop/chat
  history. The model brief is not forwarded as authority or as agent context in this slice.
  Remote task/resync records omit the new brief, and result evidence stays owner-local.
- Shared full-app/widget task evidence now displays the original owner request and a separate
  labelled SORA suggested brief, alongside existing readable result/errors/evidence coverage.
- Routed `pose`/`move` to the existing authorized avatar dispatcher without allowing coordinates.
  Passive image-on-prompt/adaptive context no longer consumes a selected motion request. Static
  avatar-off removes those variants; a fresh epoch check precedes dispatch. Replies and trace
  states distinguish command dispatch from animation completion or walking arrival.
- Fixed a regression discovered here: `create a new Python module` bypassed the missing-project
  boundary. File-authoring classification now recognizes language-qualified modules/scripts and
  precedes greeting/status/offline fast paths, so these markers cannot bypass project checks.
- Added a clearly labelled isolated offline GUI fixture, with no real agent/model inference or
  authoring, plus 22 companion-call tests and four additional routing regression cases. Exported
  the new schema and updated plans, tracker and agent runbook additively.

## Verification

- Final `scripts/verify.ps1` under `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003`:
  **634 Python passed, 24 opt-in skipped**, **8 PWA checks passed**, Ruff, mypy (251 files),
  generated-schema check and compileall passed. Final pytest elapsed **93.31 seconds**.
- `dotnet test clients/csharp_tests/csharp_tests.csproj --no-restore`: **41 passed**.
- Both desktop projects build with **0 warnings / 0 errors** after the final evidence UI change.
- QA script Ruff passed; `mypy src tests scripts/export-contracts.py scripts/verify-companion-calls.py`
  passed for **252 files**. A standalone script-only mypy invocation did not resolve typed local
  sources; the explicit source-inclusive check resolved that invocation issue without suppressions.
- Deterministic integration covers original-request authority, model/default selection, no prior
  desktop-history forwarding, queued-not-completed receipt, same-nonce replay rejection, unknown
  reference/harness rejection, remote isolation, static-off, pre-selection Stop, off/on during
  atomic admission, missing write project, result privacy and existing pose/walk queues.
- Computer Use captured the isolated full-app GUI, clearly showing **Offline test model**, zero
  runs, Chat/Activity/Settings/3D navigation and ordinary Send/delegate/attachment controls. The
  first draft action failed with **failed to activate captured window**; fresh window selection
  and activation recovery failed too. No further UI input was attempted. Chat-to-Activity/result
  acceptance, including the final owner-request label, is **not verified** by this attempt.
- QA Core exited normally through its STOP sentinel and cleanup; its GUI process was stopped by
  verified QA command-line identity after activation failed. Port 18793 has no listener, owner
  `sora.exe` PID 52000 remains alive and was not restarted/reconfigured. QA artifacts retained in
  `.local/companion-call-gui-qa-20261003`; no real LLM inference was performed in this slice.

## Remaining work

W3 stays in progress: actual small-model vocabulary/negative-intent acceptance; full/compact/PWA
and voice chat-to-delegation GUI acceptance; unified action result/lifecycle integration and
remaining look/point/press/type executors/verifiers; editable multi-model purpose shortlists;
successful live project/changelog completion, each adapter boundary and other open plan gates.
Prompt instructions against quoted/negated/injected tasks are not a proof of perfect intent
classification or adversarial robustness. This slice does not claim arbitrary desktop control,
complete file-read auditing, verified specialist entitlement or overall frontend completion.

Details: [verification](../docs/verification/W3_COMPANION_CALLS_GPT-6-Astra_2026-10-03.md).
