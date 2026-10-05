# Native-app-only decision and integrations CLI design

Model name: **Opus 5.5**. Checkpoint **2026-10-05 19:54:39 +01:00**, Europe/London. Status:
**documentation only**. It records two owner decisions and a new design. No code, test or earlier
record was changed or deleted.

## Changes

- **Owner decision: only the native app.** In the owner's words, "for now, there should only be
  the native app (which may consist of multiple windows)". The Shell host is SORA's only active
  client. The full app, widget and PWA are frozen: kept and still building, but not developed,
  and with no parity gate. P15.7 is marked superseded.
  - Recorded in `VISION.md` (principles), `V1.md` (ground rules), `README.md` (layout table and
    quick start) and the realignment.
- **Owner decision: integrations.** P15.11 becomes V1 custom agent endpoints. P15.10 becomes an
  owner-facing CLI for building integrations, after V1. Realignment conflicts 2 and 3 are
  marked resolved.
- **New `docs/plans/INTEGRATIONS_CLI_DESIGN_2026-10-05.md`** (architecture left to me by the
  owner):
  - integrations are out-of-process **MCP servers** plus a SORA manifest that adds the
    decision-layer family, an `observes` or `changes` effect, and example prompts;
  - a new Core `IntegrationHost` module supervises them, registers their tools, and enforces the
    ask-first rule for tools that change things;
  - stimuli arrive at `POST /api/v1/extensions/{id}/events`, replacing the P08.6 fake extensions.
    The `/api/v1/integrations/` prefix is taken by P07 rollback;
  - a `sora dev` CLI acts as a thin client over the authenticated local API, offering internals
    inspection, an event tail, context and tool previews, and integration management;
  - five phases, I1–I5. I1 (read-only internals) could optionally help V1 debugging.

## Verification

Relative Markdown links across the repository: 0 broken. No code changed, so no test run was
needed.

## Limits and next

Open choices (to decide at I2): use the official MCP SDK or hand-write the client; whether
pre-approval is per tool or per integration; whether integrations may add GUI surfaces.
Implementation has not started.
