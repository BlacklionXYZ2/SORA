# Integrations and the SORA developer CLI — design

Designed by **Opus 5.5**, 2026-10-05, at the owner's request. The owner asked for "a CLI tool
that provides access to SORA's internals to create integrations for her" and left the
architecture open. This document replaces the public-SDK framing of P15.10 and P15.11 (see the
[realignment](V1_REALIGNMENT_2026-10-05.md)).

**Status: design only.** This is **after-V1** work under [VISION.md](../../VISION.md), apart from
the optional slice I1 below.

## What an integration is for

An integration gives SORA something new **she herself** can use:

- **Tools:** things she can do or look up, such as controlling Spotify, reading the weather,
  querying a game's API or toggling a smart light.
- **Stimuli:** events she can notice and react to, such as "build failed", "a friend came online"
  or "a timer finished".

This is different from the V1 **custom agent endpoints**. An agent endpoint is a colleague she
hands a whole task to. An integration is a tool in her own hands. Both are configured by the owner.

## Architecture

```text
 sora dev …  (CLI, thin client)          Settings → Integrations (later)
        │  owner token, loopback HTTP           │
        ▼                                        ▼
 ┌──────────────── SORA Core ────────────────────────────────┐
 │  existing local API ── IntegrationHost (new module)       │
 │                          │ supervise / call / events      │
 │  tool registry ◄─────────┤                                │
 │    → decision layer → brain                               │
 │  ask-first gate ◄────────┘ (tools that change things)     │
 └───────────┬────────────────────────────────────────────────┘
             │ MCP over stdio or local HTTP
   ┌─────────┴──────────┐
   integration process   integration process  (any language)
```

### 1. An integration is an MCP server plus a SORA manifest

- **MCP (Model Context Protocol)** is the standard way to give models tools. It works in any
  language, it runs out of process (a crashing integration can't take SORA down), and Cody,
  Claude and the others already know how to write MCP servers. Many existing MCP servers can be
  plugged in unchanged.
- The **manifest** (`sora-integration.toml`) adds what SORA needs and MCP doesn't describe:

```toml
id = "spotify"
nickname = "Spotify"
description = "Control music playback on this PC"
command = ["python", "server.py"]        # or url = "http://127.0.0.1:7801/mcp"

[[tools]]
name = "pause"
family = "media"                          # capability family the decision layer chooses from
effect = "changes"                        # "observes" or "changes" (changes → ask-first rule)
examples = ["pause the music", "stop Spotify for a sec"]

[[events]]
name = "track_changed"
description = "A new song started"
```

- `family` and `examples` feed the **decision layer**. Families are what System-1 chooses
  between, and the example prompts double as training and evaluation data for the Laya
  fine-tune. Every integration therefore improves the router's dataset.
- Secrets never go in the manifest. They are referenced by name and stored in Core's existing
  secret configuration.

### 2. Core side: `IntegrationHost`

A new focused module, not more methods on `SoraRuntime` (see [AGENTS.md](../../AGENTS.md)). It:

- starts and stops integration processes, checks their health, and restarts crashed ones with
  backoff;
- reads each server's tool list, checks it against the manifest, and registers the tools in
  SORA's tool registry so the decision layer and brain can see them;
- routes her tool calls, with timeouts and results labelled honestly (`ok`, `failed`,
  `unknown`);
- **enforces the vision's autonomy rule in Core.** A tool with `effect = "changes"` cannot run
  until the owner agrees, unless the owner pre-approved that tool in Settings. This guards
  against the small brain, as [VISION.md](../../VISION.md) asks;
- accepts **stimuli** at `POST /api/v1/extensions/{id}/events`. The `/api/v1/integrations/` prefix
  is already used by P07's workspace-integration rollback, and the `/api/v1/extensions` routes
  are the P08.6 ones this design replaces. Events become desktop-awareness input for the brain;
  they are never instructions;
- records every call and event in the existing trace and event log.

The existing P08.6 "extensions" (two built-in fakes with grant-gated enable) are superseded by
this.

### 3. The CLI: `sora dev`

A subcommand group of the existing `sora` entry point. It is a **thin client over the existing
authenticated local API**, built on `sora.api.client`. It never opens SQLite directly, because
Core owns state. It is owner-only: loopback plus the owner token file, as the GUI uses. Output
is readable tables by default, with `--json` on everything so agents and scripts can use it.

| Group | Commands | Purpose |
|---|---|---|
| Internals | `inspect state`, `inspect tasks [id]`, `inspect memories`, `inspect traces <task>`, `inspect settings`, `inspect agents` | See what SORA knows and is doing |
| Live view | `events tail`, `say "<text>"` | Watch her event stream; talk to her from the terminal |
| Brain preview | `context preview "<prompt>"`, `tools preview "<prompt>"` | Show exactly what the brain would receive, and which tools the decision layer would offer, for a prompt. The main debugging tool for tool-calling quality |
| Integrations | `integration new <name> [--lang python\|node]`, `validate`, `install <path>`, `list`, `enable`, `disable`, `reload`, `logs <id>` | Scaffold, check and manage integrations |
| Testing | `integration call <id> <tool> --args '{…}'`, `integration emit <id> <event> --data '{…}'` | Run a tool or fire an event by hand, bypassing the brain |

`integration new` scaffolds a working MCP server, its manifest and a test, so an agent can be
asked to "make an integration for X" and has a correct starting point.

## Phases (after V1 unless the owner pulls I1 forward)

| Phase | Delivers | Size |
|---|---|---|
| **I1** internals CLI | The `inspect`, `events tail`, `say` and `context preview` commands over existing routes (plus a read-only context-preview route) | Small. **Could help V1 debugging**; owner's choice |
| **I2** integration host | Manifest, MCP client, supervision, tool registration, ask-first gate, `integration install/list/enable/disable/call/logs` | Medium |
| **I3** stimuli | Events endpoint, event handling in her awareness input, `integration emit` | Small |
| **I4** authoring and GUI | `integration new` scaffolds, `validate`, and an Integrations page in Settings reading the same registry | Medium |
| **I5** decision layer | `tools preview`, plus export of manifest families and examples as decision-layer data | With the Laya work |

## Open choices (decided when I2 starts)

- **MCP client library.** Use the official MCP Python SDK, or hand-write the small JSON-RPC
  client, as SORA already does for Hermes (ACP) and Codex? Core currently has only three runtime
  dependencies, so this is a real trade-off.
- **Pre-approval granularity** for `changes` tools: per tool, or per integration.
- Whether an integration may add **GUI surfaces** (panels, desktop objects) as well as tools.
  That is deliberately out of scope until the GUI is stable.
