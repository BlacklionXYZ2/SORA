# W2 / W3 — specialist catalogue and explicit selection

Contributor model name: GPT-6.1-Sol
Slice completed: **2026-10-03 09:19:15 +01:00 (Europe/London)**.
Overall frontend goal and W2/W3 workstreams: **in progress**, not complete.

## Implemented

- Added owner-local cached agent catalogue GET and explicit metadata Refresh POST. Deduplicates
  adapter aliases; coalesces concurrent refreshes; bounds discovery and stops its owned processes.
  Closing Core cancels outstanding refresh. Backend errors are sanitised rather than exposing
  provider configuration/credentials. Remote callers cannot access these inventory routes.
- Catalogue separates exact model IDs, display names, provider descriptions, desired owner roster,
  configured defaults, supported efforts, embedded tiers and checked time. Listing is labelled
  provider-listed, never inferred entitlement or successful inference. Existing provider capability
  flags are shown as adapter declarations, not as new tools implemented by this slice.
- Codex discovery follows bounded pagination, detects bad cursors and includes hidden catalogue
  entries. Explicit request model/effort reaches thread start/resume and turn start. If the thread
  response explicitly reports a different pinned model, no task prompt is sent.
- Hermes discovers ACP session models without a prompt and with configured MCP startup disabled.
  The metadata probe denies permission requests. Task model pins use session/set_model before the
  prompt on both fresh and resumed sessions; defaults are not rewritten. Rejected switches fail
  visibly. Per-run reasoning effort is unsupported, not silently ignored.
- Antigravity discovers models through agy models; fixed a real first-chunk truncation bug by
  draining stdout to EOF under a byte/time limit. Explicit model arguments preserve exact IDs;
  embedded effort tiers cannot silently override conflicting requested effort.
- Added optional bounded model/effort fields to task persistence and provider requests. Overrides
  require an explicit agent route. Idempotent retries cannot reuse a key with a different selection.
  Explicit selections never use auto-route fallback. Removed the hidden default-adapter fallback
  for a missing registered agent, including persisted runs; failures release the lease normally.
- Shared Windows Agents and models window: full app Activity entry, compact menu entry and both
  Delegate buttons. Inspect cached catalogue, refresh without inference, choose agent/model/effort,
  review the exact request and submit. Cancel preserves the draft; retry within the selector keeps
  its submission key. A disappearing listed choice is not silently replaced with a model pin.
- Activity displays requested model/effort, explicitly not execution verification. Fixed clipped
  catalogue notice, modeless Close, widget-owner topmost ordering and wrapped Activity row heights
  found through actual GUI review.
- Added reproducible metadata/local-fixture QA harness, Python transport/persistence/error tests,
  one C# request-body regression, regenerated contracts and a user-facing agent-model runbook.

## Verification

- Final scripts/verify.ps1 in dedicated .local/frontend-verify-20261003 environment:
  **593 passed / 24 opt-in skipped**, 102.87 seconds; **8 PWA passed**. Ruff, mypy (241 files),
  contract freshness and compilation passed.
- **41 C# tests passed**; full app and widget builds: **0 warnings / 0 errors**.
- Real installed metadata discovery: Codex **7**, Hermes **22**, Antigravity **18** entries.
  Hermes includes openai-codex:gpt-6-luna, gpt-5.6-terra and gpt-5.6-luna; DeepSeek is advertised
  as deepseek:deepseek-flash, not a version-verified v4.1 identifier. Do not equate that alias with
  the requested version without execution/provider evidence.
- Computer Use: full app exposes all 18 Antigravity entries; both clients selected fixture-small
  with low effort and completed distinct deterministic tasks. Receiving adapter proof, stored task
  selection and completed Activity rows agree. Compact cancellation preserved its draft; explicit
  Refresh completed; final notice/topmost/row-height and modeless Close repairs reviewed.
- No live agent inference/entitlement probe occurred. The dialogue provider in GUI QA was offline;
  the synthetic specialist was clearly labelled. No claim that Gemini/DeepSeek/ChatGPT performed
  these fixture tasks. Native provider selection RPC/CLI mappings were tested with fake transports.
- QA Core/client processes closed; port 18793 released. Original owner Core PID 52000 remained
  alive and untouched. QA Core restarts were forced, not graceful-shutdown acceptance. QA files
  remain isolated in .local; no owner conversations or provider defaults were changed.

## Still required

Editable catalogue purposes/preferences in the unified settings store; compact companion-facing
delegation schema and catalogue; per-task project root and equal/nested writer leases; live low-cost
provider selection/execution evidence and last-success provenance; complete progress/result,
follow-up/resume/cancel GUI paths and remaining W1–W6 acceptance. Do not close the overall goal.

[Detailed evidence](../docs/verification/W2_W3_AGENT_CATALOGUE_SELECTION_GPT-6-Astra_2026-10-03.md).
