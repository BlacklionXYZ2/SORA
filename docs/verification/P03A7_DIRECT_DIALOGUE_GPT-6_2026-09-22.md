# P03A.7 direct dialogue acceptance — GPT-6

Completed: **2026-09-22 19:41:47 +01:00 (Europe/London)**.

## Implementation and downstream connection

- `--dialogue-backend`, `--dialogue-model`, `--dialogue-base-url` and
  `--dialogue-timeout` select a direct model independently of the existing `--provider`
  reasoning harness. `SORA_DIALOGUE_API_KEY` is read from the process environment as a protected
  value. The default remains deterministic.
- The asynchronous OpenAI-compatible Chat Completions adapter accepts HTTPS or loopback HTTP
  `/v1` endpoints, validates a bounded text result, and reports sanitized failures. It does not
  grant the model direct repository, desktop or tool access.
- Core compiles canonical identity and six recent conversation messages into bounded direct
  context. It resolves a relevant read-only `sora.tasks.show` capability, executes the task-status
  read itself, and adds a six-task bounded snapshot. A selected capability name alone cannot
  invoke an arbitrary action. Text user/assistant messages and their replay events commit in one
  SQLite transaction after a successful reply; provider failure leaves no half turn.
- Existing P08 API, P14 semantic voice sessions and P15.1 PWA dialogue use this same runtime
  provider. The redacted settings projection shows backend/model/endpoint and key presence.
  A paired remote session needs `conversation:read` to contribute prior history and `tasks:read`
  to contribute task status, in addition to its authorized `conversation:write` turn.
- P06 specialist routing, steering and result provenance remain separate. P15.6 compact widget
  and P15.7 full app can now consume the direct dialogue path; their own UI acceptance remains
  open. Earlier P15.4 integrated scenarios used deterministic dialogue and are not retroactively
  described as live-model tests.

## Deterministic verification

- `tests/providers/test_direct_dialogue.py`: six cases for Core context and task-status selection,
  simultaneous specialist work, remote scope exclusion, failure atomicity, the HTTP wire contract,
  independent backend configuration and key redaction.
- Focused direct/companion/voice/API/remote suite: **36 passed**.
- `scripts/verify.ps1`: **346 passed, 10 existing opt-in native/Unity skips**; Ruff passed;
  strict mypy passed across **186 source files**; schema freshness and compileall passed;
  browser PWA checks **7/7** passed.
- `uv lock --check` passed. A clean wheel built, installed with 12 resolved packages including
  `httpx 0.28.1`, and executed `python -m sora --state` against an isolated state root; schema
  version 7, zero tasks and zero leases were reported.

## Separately labeled live local-model smoke

LM Studio's loopback server was started on `127.0.0.1:1234`. The installed
`qwen3.5-0.8b` model was loaded as the temporary API identifier `sora-p03a7-smoke`.
SORA ran with `--provider deterministic --dialogue-backend openai-compatible` against that
endpoint. An interactive user turn returned:

> I understand your request for a short reply and can assist you with that.

An independent `--messages` read showed one user record followed by one assistant record,
with assistant provenance `direct dialogue: openai-compatible`. The runtime state for this
smoke is under `.local/p03a7-live-smoke`. The temporary model was unloaded and the server
stopped after the check.

This proves a real local model request and canonical turn persistence through the direct
adapter. It does not establish dialogue quality, cloud-provider credentials, live spoken
audio, remote phone acceptance, or streaming tokens before durable finalization. The provider
currently yields finalized response chunks to the CLI; true token-by-token client streaming
is a separate improvement.

No Git commit, tag or staging operation was performed.
