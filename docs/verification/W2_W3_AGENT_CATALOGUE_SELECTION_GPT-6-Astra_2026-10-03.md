# Specialist catalogue / explicit selection evidence

Contributor: GPT-6 Astra. Slice completed **2026-10-03 09:19:15 +01:00**.
Status: bounded slice implemented and verified; full catalogue/W2/W3/frontend alignment open.

## User-facing paths

Full app: Activity → Agents and models… for metadata; Chat → Delegate as task for selection.
Compact: ••• → Agents and models…; Delegate opens the same selector with the current draft.
Model discovery is explicit, not a recurring background inference test. Cached opening sends no
prompt. Refresh shows its working state and completion message. Hermes requires one empty ACP
session to expose models; configured MCP startup and metadata permission approval are disabled.

Each selection has agent, model and supported effort. The default option is labelled as configured
default, not a pinned model. Antigravity IDs already encoding a tier disable a second effort override.
Hermes offers no effort override because its per-session mapping is not implemented. Codex efforts
come from returned metadata; a listed model's recommended effort is selected explicitly where given.
Final confirmation shows the actual choice. Activity shows the requested selection, not a verified
claim about the backend's executed model. SORA's local dialogue model is unchanged.

## Fresh evidence

| Check | Result and boundary |
|---|---|
| Codex metadata | 7 entries, all pages handled; no inference access tested |
| Hermes metadata | 22 entries via native ACP; no prompt; empty native sessions may exist |
| Antigravity metadata | 18 entries; live check found first-read truncation, fixed and retested |
| Full-app model list | All 18 Antigravity entries visible in dropdown via Computer Use |
| Full-app submission | fixture-small / low, task-79c2330a-6d2c-4dfd-8f68-bfd922561f65 completed |
| Compact submission | fixture-small / low, task-a0b82ca2-4afc-423a-9c49-4a9ba2e0d7c3 completed |
| Host receipt | Both adapter proofs contain exact selected model/effort; persisted API task matches |
| Compact cancellation | Escape closed selector and preserved exact draft; no additional task started |
| GUI refresh | Discovering state then Metadata refreshed, with no specialist task/inference |
| Layout/close repairs | Whole notice visible; compact modal not covered by owner; Activity rows auto-size; modeless Close returned to Activity |
| Missing adapter | Regression: persisted pinned run fails, default start_count=0, lease_count=0 |

The actual Hermes roster includes subscription IDs openai-codex:gpt-6-luna,
openai-codex:gpt-5.6-terra and openai-codex:gpt-5.6-luna, and DeepSeek alias
deepseek:deepseek-flash. The alias alone does not establish DeepSeek v4.1. Antigravity lists
gemini-3.8-flash-high/medium/low. The GUI does not silently invent a backend ID from display names.

Local evidence retained:

- [.local metadata proof](../../.local/agent-catalogue-final-probe-20261003/catalogue-proof.json).
- [Full-app receiving-adapter proof](../../.local/agent-catalogue-qa-20261003/full-app-selection-proof.json).
- [Compact receiving-adapter proof](../../.local/agent-catalogue-qa-20261003/widget-selection-proof.json).
- Isolated QA SQLite state: .local/agent-catalogue-qa-20261003/data/sora.db.

Computer Use helper occasionally returned stale UIA trees, unavailable geometry or a cached-element
error. Fresh window/geometry captures and keyboard confirmation recovered. These failures were
not treated as task completion. Final successful modeless Close and row-sizing captures used the
final rebuilt full app; compact topmost repair used the rebuilt widget.

## Automated verification

Final command: scripts/verify.ps1 with UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003.
593 passed / 24 opt-in skipped, 102.87s; 8 PWA checks. Ruff/mypy/contracts/compilation passed.
Dedicated harness Ruff/mypy also passed. 41 C# tests passed; both Windows client builds had no
warnings/errors. No Unity source changed and no new Unity/physical-device acceptance run occurred.

Test coverage includes exact fresh/resumed Codex parameters, cursor continuation/rejection, Hermes
session switch ordering/rejection before prompt, unsupported effort, Antigravity embedded tier
conflict and all stdout chunks; cached/single-flight/deduplicated inventory, sanitised failure,
owner-only routes, task persistence/restart, selection idempotency and no hidden default fallback.

## Scope and cleanup

QA Core used loopback 18793 and a dedicated state directory. Real providers were used only for
metadata. The GUI delegated to a deterministic QA fixture with no file tools, not a paid/free LLM.
No model was reloaded, credential changed or owner Core restarted. Verified QA process trees were
closed and the port released; owner sora.exe PID 52000 remained running. Forced QA Core termination
is not graceful-shutdown evidence. QA native sessions/fixture records were not deleted or archived.

Still open: editable purposes/defaults in canonical settings, last-success evidence, compact tool
schema for SORA herself, actual live provider pins, task project directory/lease handling and full
progress/follow-up/cancel/results user paths. Other frontend checklist rows remain unchanged.

Official Codex metadata semantics were checked against [App Server documentation](https://learn.chatgpt.com/docs/app-server)
and the [catalogue-versus-entitlement guidance](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).
