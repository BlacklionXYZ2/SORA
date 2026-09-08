# P04 Hermes live verification and hardening

- Stage: P04 — First live reasoning adapter: Hermes
- Verified: 2026-09-08 (Europe/London)
- Completion timestamp: 2026-09-08 08:29:02 +01:00
- Model performing audit: GPT-5.6 Sol
- Result: pass for the original bounded reasoning matrix; trust-policy amendment recorded below

## Verified Hermes installation

| Item | Evidence |
|---|---|
| Product | Hermes Agent |
| Local version | `0.21.0` (`2026.8.31`) |
| Local source revisions | upstream `fef0e16f`; local `9dd6634c` with one carried commit |
| Installation | Git installation; Python 3.11.16; OpenAI SDK 2.24.0 |
| ACP probes | `hermes acp --version` returned `0.21.0`; `hermes acp --check` returned `Hermes ACP check OK` |
| Configured live route | ChatGPT/Codex subscription authentication; configured model `gpt-5.6-luna` |
| Update state | The installation reported 690 upstream commits available. It was deliberately not mutated during verification, so these results apply to the exact local revision above. |
| Terms | Hermes Agent repository license is MIT |

`hermes doctor` passed the core installation/provider checks but reported two npm dependency issue
categories in Hermes' optional browser/web tooling workspace. SORA did not alter or update that
external installation.

No token, credential value, private prompt body, or private runtime row content is included in this
report. Hermes' own status command confirmed authentication; SORA did not copy credentials into its
state or repository.

## Evidence-backed capability matrix

| Surface | Hermes 0.21.0 | SORA P04 mapping and evidence |
|---|---|---|
| Transport | ACP v1 JSON-RPC over stdio | `initialize`, `session/new` or `session/load`, `session/prompt`, and `session/cancel` are mapped. Negotiated protocol versions other than 1 fail closed. |
| Authentication | Reuses configured Hermes provider and credentials | Inherited by the child process; no credentials enter normalized results, patches, or traces. |
| Sessions | New, load/resume, list, fork, and persisted history are available in Hermes | New sessions and native `session/load` resume are mapped. The adapter retains a bounded native-session lookup. Resume was verified live with the same session ID. |
| Streamed updates | Hermes emits response, thinking, tool, and permission activity | SORA consumes response chunks internally. `ProviderCapabilities.events` is false because `events()` does not expose a SORA stream. |
| Cancellation | ACP `session/cancel` interrupts the active prompt | Protocol cancellation, grace period, terminate, and kill fallback are implemented. Cancellation was verified live. |
| Permissions/tools | Hermes ACP has native tools and ACP permission requests | Native-tool updates are accepted and `allow_once` is selected when offered. `--hermes-deny-approvals` is an explicit restricted mode. SORA reports `tool_restrictions=false` because Core grants do not narrow Hermes' native toolset. |
| Working directory | ACP binds file/terminal tools to the session cwd | CLI requires an explicit existing `--hermes-cwd`; the bounded tests used a dedicated ignored workspace that remained empty. |
| Configured MCP | Hermes normally starts globally configured MCP servers | The default child environment preserves them. `--hermes-skip-configured-mcp` sets `HERMES_ACP_SKIP_CONFIGURED_MCP=1` only when explicitly requested. |
| Structured results | Hermes returns streamed natural-language content | SORA prompts for a bounded JSON envelope, accepts fenced JSON, validates known fields, bounds collected output, and converts only validated fields into Core contracts. |
| Steering | Hermes internals expose more lifecycle operations than P04 maps | Not supported by the SORA adapter and reported truthfully. |

Official references used for this matrix:

- [Hermes ACP Host Integration](https://hermes-agent.nousresearch.com/docs/user-guide/features/acp)
- [Hermes ACP Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/acp-internals)
- [Hermes Programmatic Integration](https://github.com/nousresearch/hermes-agent/blob/main/website/docs/developer-guide/programmatic-integration.md)
- [Agent Client Protocol v1](https://agentclientprotocol.com/protocol/v1/initialization)
- [Hermes Agent MIT license](https://github.com/NousResearch/hermes-agent/blob/main/LICENSE)

## Changes made during verification

- Corrected capability advertising: SORA now reports native resume as supported and provider events as unavailable until a real `events()` stream exists.
- Added native session-ID capture and `session/load` resume. A first live resume exposed replayed history being concatenated with the new response; the adapter now discards load-time replay before collecting the resumed turn.
- Sends ACP `session/cancel` before bounded terminate/kill fallback and makes repeated `start()` calls idempotent.
- Requires explicit Hermes working-directory selection before SORA initializes its database.
- Preserves Hermes' configured MCP startup and native tools by default; adds explicit approval-denial and MCP-skip switches for restricted runs.
- Accepts native tool activity and answers ACP permission requests with `allow_once` when offered. ACP client filesystem/terminal calls remain unsupported because SORA does not implement those editor-side methods.
- Enforces ACP protocol v1 negotiation and a 65,536-character default output ceiling.
- Rejects malformed known list fields rather than silently dropping them; preserves valid `files_read`, `commands_run`, and `warnings` fields.
- Treats model-suggested facts as `inference` with confidence `0.5`, not certain observations, and corrects owner-only patch scope to `owner`.
- Makes runtime timeout wording provider-neutral and labels the interactive backend accurately.
- Adds conformance coverage for launch failure, exact ACP exchange, environment, start idempotency, result parsing, output bounds, accepted native-tool updates, permission selection, protocol cancellation, resume, and CLI cwd validation.

## Bounded live scenario evidence

The live matrix used an ignored, dedicated SORA state root and an isolated empty Hermes workspace.
Prompts explicitly prohibited tools. The configured external model was invoked; this is live-provider
evidence, not a mock claim.

| Scenario | Result |
|---|---|
| Core vertical slice | completed; dialogue remained responsive while the Hermes task ran |
| Normalized result and patch | one normalized result, one proposed fact, and one applicable patch persisted through Core |
| Trace coverage | six correlated runtime phases persisted |
| Native session identity | captured successfully |
| Resume | completed through `session/load`; returned the same native session ID |
| Cancellation | completed with final status `cancelled` |
| Workspace containment observation | zero files present after the matrix |
| Database checks | `PRAGMA quick_check=ok`; schema v4; no remaining runtime lease |
| Epistemic metadata | persisted fact: `inference`, confidence `0.5`, provenance `Hermes ACP normalized result` |

An earlier matrix run caught the history-replay defect described above and therefore was not treated
as acceptance. The corrected matrix passed. The live calls created native Hermes session history in
Hermes' own user state; no deletion was attempted because that is external persisted state.

## Repository and installed-artifact verification

- Ruff: passed.
- Strict mypy: passed across 56 source files.
- Schema freshness: passed.
- Pytest: **78 passed in 3.94s** in the final working-tree verification run.
- Compileall: passed.
- Fresh sdist and wheel: built successfully.
- Fresh Python 3.12 wheel environment: import and capability probe passed with
  `sessions=true`, `resume=true`, `events=false`, and `tool_restrictions=false`.
- Installed CLI guard: missing `--hermes-cwd` exited 2 and did not create a database.

## Trust-policy amendment and scope boundary

On 2026-09-08, the user clarified that Hermes is a trusted agent harness and should manage its own
tools in the same way Codex and Antigravity manage theirs. The adapter was amended accordingly:
native tool activity is no longer rejected, configured MCP integrations remain available by default,
and ACP permission requests select `allow_once`. Credential-free fake-ACP conformance proves those
wire behaviors.

The original live start/resume/dialogue/cancellation/patch matrix remains valid, but it explicitly
asked Hermes not to use tools. Three later live native-tool probes (one 30-second and two 120-second
runs, with configured MCP both enabled and skipped) reached their deadlines without a completed
result or workspace change. They are recorded as timeouts, not tool-success evidence. Therefore P04
proves the trusted configuration and protocol behavior but does not claim a completed live native-tool
scenario. The assigned Hermes cwd remains a scope boundary, not an OS sandbox, and
`tool_restrictions=false` remains the truthful capability value.
