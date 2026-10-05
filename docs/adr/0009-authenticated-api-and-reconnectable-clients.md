# ADR 0009: Authenticated API and Reconnectable Clients

- Status: accepted; P08 complete
- Date: 2026-09-08
- Completed: 2026-09-08 20:45:00 +01:00
- Model: Gemini 3.8 Flash

## Context

Phase P07 established multi-candidate workspace synthesis and human-gated code review. However, access to SORA Core remained strictly internal (CLI and programmatic runtime calls). To achieve Gateway G3 ("Independent Client Interface"), SORA required a secure, reconnectable client boundary:
1. Unified Protocol: A standardized HTTP/1.1 and RFC 6455 WebSocket interface exposing tasks, messages, workspaces, reviews, and health/readiness probes without adding third-party web framework dependencies.
2. Reconnectable Event Streaming: Clients must be able to disconnect and reconnect independently without terminating ongoing tasks. Missed events must be replayed from the durable `events` table by sequence cursor, with automatic deduplication (`classify_event_order`) and full resynchronization snapshots when cursors expire or gaps occur.
3. Local Security Boundary: The server must bind exclusively to loopback addresses (`127.0.0.1`) by default, authenticate via Bearer tokens, strictly forbid credentials in URL query parameters (preventing accidental exposure in URL logs/history), and validate Host/Origin headers against authorized local origins.
4. Client Supervision: Slow or uncooperative WebSocket clients must be dropped cleanly with policy violations (close code 1008) to prevent memory accumulation or stalling Core message processing.
5. Projections and Extensibility: Companion dialogue state must be projected separately from background worker activity, configuration settings must redact secrets (`***REDACTED***`), desktop objects (Kanban boards) and semantic verbs must be queryable, and external extensions must be registered with clean enable/disable lifecycle and active capability invalidation.

## Decision

### 1. Dependency-Free Protocol Engine (`sora.api.protocol`)
- Implement RFC 7230 HTTP/1.1 parsing and RFC 6455 WebSocket framing natively on top of Python standard library `asyncio.StreamReader` and `asyncio.StreamWriter`.
- Implement full WebSocket framing support: text frames (opcode 0x1), close frames (opcode 0x8), ping/pong heartbeats (opcodes 0x9/0xA), payload masking/unmasking, and standard 101 Switching Protocols handshake using SHA-1 and GUID `258EAFA5-E914-47DA-95CA-C5AB0DC85B11`.

### 2. Local Security Boundary (`sora.api.auth`, `sora.api.config`)
- Loopback binding validation: `ApiServerConfig` enforces that host is a valid loopback address (`127.0.0.1`, `localhost`, or `::1`).
- `TokenAuthenticator`: Validates constant-time Bearer token headers (`Authorization: Bearer <token>`). Tokens must satisfy minimum entropy requirements.
- `SecurityValidator`: Strictly rejects requests containing credentials in URL query strings (`token`, `auth`, `key`, `access_token`, `bearer`, etc.), raising `ApiSecurityError` (HTTP 400).
- Host and Origin validation: Enforces that `Host` and `Origin` headers match allowed loopback origins, raising `ApiForbiddenError` (HTTP 403) on cross-origin unauthorized origins.

### 3. Snapshot, Replay, and Reconnection (`sora.api.events`, `sora.api.server`, `sora.api.client`)
- Event replay: When a client connects with a sequence cursor (`since_sequence`), `_handle_websocket_upgrade` replays missed events directly from the durable SQLite `events` table in strict ascending sequence order.
- Gap/Expiration resync: If `cursor_seq < 0` or precedes the minimum available sequence in the stream, the server responds with a `resync_required` message containing an authoritative state snapshot (`build_state_snapshot`).
- Deduplication and ordering: Live broadcasting and client event streams use `sora.contracts.events.classify_event_order` to detect duplicate deliveries and enforce strict monotonically increasing sequence numbers. Stale frames are safely discarded.
- Backpressure protection: `EventBroadcaster` monitors per-client queue capacity. If a slow client fails to drain its buffer, it is disconnected with WebSocket close code 1008 (`buffer_overflow_slow_client_backpressure`), preventing memory leaks and preserving Core responsiveness.

### 4. Projections and Extensions (`sora.api.routes`)
- Companion Projection (`/api/v1/projections/companion`): Projects companion dialogue readiness and active state separately from background worker task executions across specialist harnesses (`cody`, `hermes`, `antigravity`).
- Settings Projection (`/api/v1/projections/settings`): Returns runtime settings with all configured secrets replaced with `***REDACTED***`.
- Objects Projection (`/api/v1/projections/objects`): Exposes canonical desktop objects (Kanban boards with columns `TODO`, `DOING`, `DONE` ordered by insertion).
- Capabilities Projection (`/api/v1/projections/capabilities`): Exposes available semantic verbs and the list of active extension IDs.
- Extensions (`/api/v1/extensions`): Exposes registered extensions, including built-in fake Integration (`integration-media-player`) and Desktop Component (`component-kanban-board`), supporting dynamic enable and disable with immediate capability set invalidation.

## Consequences

- SORA satisfies Gateway G3 ("Independent Client Interface"): multiple authenticated clients connect, receive live event streams, disconnect independently without terminating ongoing tasks, and converge on consistent state upon reconnection.
- Core remains completely free of external HTTP framework dependencies (e.g. FastAPI, Starlette, websockets), maintaining a lean, auditable dependency tree.
- Full verification of P00–P08 achieves 175 passing tests, strict mypy typing across 105 source files, and clean Ruff formatting.

## Reversal

The API protocol and transport layers are fully modularized under `sora.api`. They can be adapted to alternative transports (e.g. Unix domain sockets, named pipes) or proxied behind production reverse proxies while preserving Core security invariants and event ordering guarantees.
