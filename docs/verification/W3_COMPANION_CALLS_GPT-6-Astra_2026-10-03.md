# W3 companion-call progress evidence — GPT-6 Astra

Checkpoint **2026-10-03 14:21:58 +01:00** (Europe/London). W3/W2 and the frontend goal remain active.

## Delivered contract and flow

`CompanionCall` shares W4's strict native/file read variants. Implemented additions are:

| Operation | Model supplies | Core resolves/does | Current evidence |
| --- | --- | --- | --- |
| `list_agents` | harness or auto, optional listing cursor | cached enabled catalogue, pages of 8 model refs, purposes and states | deterministic cache/result-envelope tests |
| `delegate` | bounded suggested task, harness/auto, optional project/model refs | original owner intent, exact selections, static policy, project validation, atomic task/run/receipt | deterministic runtime and privacy tests |
| `pose` | wave/sit/lean/climb/stand keyword | existing avatar presentation dispatcher | controlled authorized queue tests, not live animation completion |
| `move` | pointer only | samples Core-owned pointer, existing move dispatcher | controlled move queue, not actual arrival |
| `finish` | no action fields | normal conversation; no second unified motion decision | regression test |

No arbitrary shell/coordinates/model authority is added. The local chooser receives only enabled
schema variants; static-off and remote sessions do not gain these effects. Existing legacy read
providers continue to work. Read/list results carry their source/status/timestamp; `list_agents`
also uses the existing versioned result envelope. Terminal effects receive Core-owned versioned
trace IDs and honest queued/dispatched/failed states; the complete future W3 action-result and
verification lifecycle is not closed by this implementation.

The catalogue reuses canonical agent defaults and cached metadata, not another provider store.
Purpose text is descriptive/untrusted data. Provider-listed/configured models are not execution
entitlements. Default model refs are exposed in initial context; other model refs require their
discovery page. A literal project path or unknown ref is rejected. Cached project refs select a
known configured destination; a missing local write destination asks **Which project?**

The original owner request is the durable creator message and `ProviderRequest.intent`. The
model's suggested brief is retained separately as `TaskRecord.companion_brief`, shown in the
shared readable evidence dialog, and not forwarded as agent authority/context in this slice.
Prior desktop/conversation observations are not indiscriminately sent to the delegated agent.
Owner-only evidence returns `owner_request` alongside the task/result; paired task and resync
projections omit the brief, and paired evidence access returns 403.

## Automated results

Final standard command: `scripts/verify.ps1` with the dedicated QA environment
`.local/frontend-verify-20261003` (not the running owner's locked environment).

- Python: **634 passed / 24 opt-in skipped**, elapsed **93.31 seconds**.
- PWA: **8 passed**. Ruff, mypy 251 files, schema export/check and compileall passed.
- C#: **41 passed**; full-app and widget builds both **0 warnings / 0 errors**.
- QA script: Ruff passed; source-inclusive mypy passed for **252 files**.
- 22 new tests in `tests/runtime/test_companion_calls.py`, four new routing cases. Also reran
  companion reads, legacy motion, preferences and selected-project integration.

Tests prove these particular controlled cases: strict extras/authority rejection; structural
absence of disabled variants/defs; constrained reply validation; cached/no-inference discovery;
known exposed refs; versioned list results; one terminal choice; preserved original request;
no history/brief authority forwarding; one normal chat request/receipt pair; queued wording;
same-nonce replay rejection; bad selection/no fallback; remote/static-off isolation; Stop while
selection waits; off/on between selection and database admission; missing project; remote privacy;
existing authorized pose/move dispatch; passive image capture cannot supersede those choices;
unified finish cannot trigger a second motion selector. Language-qualified module authoring and
greeting/status/offline prefixes now reach the selected-project safety path.

These deterministic cases are not real small-model intent accuracy, native effect success,
physical microphone/speaker acceptance, every adapter boundary or full adversarial coverage.
The standard suite explicitly skipped its opt-in model/native/Unity/hardware checks.

## User-side GUI attempt and limitation

Launched `scripts/verify-companion-calls.py` against dedicated state
`.local/companion-call-gui-qa-20261003` and loopback 18793, then the built full desktop app with
that token/settings path. This harness substitutes an explicitly labelled deterministic chooser
and specialist. It sends no prompt to a real LLM or provider and changes no user project files.

Computer Use observed a readable initial 780-by-525 full-app window with **Offline test model** /
zero runs, Chat/Activity/Content/Integrations/Settings/3D navigation and visible compose, attachment,
voice, Send, Look, Delegate and TODO controls. Their initial layout did not appear clipped.

The first attempt to enter the harmless exact QA prompt failed with
`failed to activate captured window`. Fresh selection plus activation failed with the same error.
Following the Computer Use skill's recovery/stop rule, no further UI input was made; no successful
chat submission or new task/result UI was observed. The final original-request label was added
after this initial observation, so its actual GUI rendering also remains unverified.

Criticism/follow-up: Send-to-SORA's automatic delegation and the manual **Delegate as task** path
need user-side comparison/help so their selection behavior is understandable. The initial layout
alone proves neither accessibility input reliability nor resulting Activity evidence. Resume the
isolated walkthrough when Windows activation works; do not substitute an API test for GUI proof.

QA Core was stopped through its sentinel and returned exit 0; the known QA GUI process was
terminated after verified command-line matching. Its artifacts remain available; port 18793 is
released. Owner Core PID 52000 remained alive, without restart/reconfiguration. No paid inference,
model download or live agent launch was attempted.

## Next acceptance/work

1. Real local small-model probes of discovery/delegate/pose/move/finish plus ordinary chat,
   negation, quotes, capability questions, untrusted observations and malformed calls.
2. Full/compact/PWA and voice shared-delegation user-side walks, result readability and Stop races.
3. Editable multi-model-purpose shortlist over the canonical settings/cached catalogue.
4. Remaining planned look/point/press/type targets, lifecycle/result envelopes and native verifiers.
5. Previously open project/changelog live completion, harness-specific boundaries, crash/alias/
   amendment and remaining frontend plan gates. Existing scope is not reduced.

[Changelog](../../changelog/2026-10-03T142158+0100_W3-COMPANION-CALLS-PROGRESS_GPT-6-Astra.md).
