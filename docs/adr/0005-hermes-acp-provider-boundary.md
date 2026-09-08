# ADR 0005: Hermes ACP provider boundary

- Status: accepted
- Date: 2026-09-07
- Trust-policy amendment: 2026-09-08

## Context

P03 proved SORA's runtime using a deterministic provider, but no live reasoning backend was connected. Hermes exposes a documented ACP stdio JSON-RPC server with session creation, streamed updates, prompts, and cancellation. SORA must consume Hermes through the versioned provider contract rather than spread Hermes-specific behavior through Core.

## Decision

Implement `HermesACPProvider` as one short-lived `hermes acp` subprocess per SORA run. The adapter owns ACP framing, session creation or loading, streamed message-chunk collection, permission responses, protocol cancellation, process cleanup, and conversion of the requested structured JSON response into `NormalizedResult` plus validated fact/memory patch proposals.

SORA asks Hermes to return only the documented result fields. Unknown fields are ignored, while malformed known fields, excessive output, and incompatible protocol versions use typed provider failures. Hermes capabilities are reported explicitly: sessions, native session resume, and cancellation are supported by this adapter. ACP updates, including native-tool activity, are consumed internally rather than exposed through `ReasoningProvider.events()`; steering is not mapped, and SORA grant/tool restrictions are not claimed.

Hermes execution requires an explicit existing working directory. Hermes is trusted to manage its own native tools and configured integrations, like the other external agent harnesses: globally configured MCP servers remain enabled by default and ACP permission requests select `allow_once` when offered. Operators can deliberately deny approvals or skip configured MCP startup through explicit CLI flags. SORA still rejects ACP client filesystem/terminal methods because it does not implement the editor-side ACP APIs; this does not disable Hermes-native file, terminal, web, memory, or delegation tools.

The deterministic provider remains the default. Hermes is selected only with `--provider hermes` or `SORA_PROVIDER=hermes`.

## Consequences

- Core remains backend-neutral and continues to mediate result acceptance and patch application.
- Credential-free conformance tests can validate the adapter with a fake ACP process.
- P04 live acceptance is installation-specific and records the exact Hermes build, configured model, isolated workspace, and bounded scenarios.
- A fresh process can load a persisted native Hermes session for resume; persistent connection pooling and steering remain future work.
- Hermes-native tool activity is accepted. SORA does not claim that its Core grants narrow those tools, and a Hermes workspace is not an operating-system sandbox.

## Reversal

Replace the adapter while preserving `ReasoningProvider`, `ProviderRequest`, `NormalizedResult`, capability reporting, and the result/patch mediation boundary.
