# GUI review + vision-alignment plan

Timestamp: **2026-10-01 12:37:32 BST (UTC+01:00)**
Model name: **deepseek-flash** (Hermes Agent)
Type: **review + plan authoring. No source code changed.**

## What changed

| Path | Change |
|---|---|
| `docs/plans/VISION-ALIGNMENT_2026-10-01.md` | New. Vision-fit plan: trust simplification (W1), path ledger (W2), chat→desktop action vocabulary (W3), perception/read tools (W4), voice in the Windows clients (W5), proactivity + GUI truth (W6), full model roster, failure modes, test plan, open questions. |
| `changelog/2026-10-01T123732+0100_GUI-REVIEW-AND-VISION-PLAN_deepseek-flash.md` | This entry. |

No other file was created, edited or deleted. `git log --oneline -1` unchanged at `89f005f`.

## Live GUI review performed (read-only against the running stack)

Reviewed the live instance at Core port 18769 (`.local/manual-test`, revision 27991) using native
Windows inspection plus **the runtime's own capture helper** (`clients/windows_capture`) — not a
foreign screenshot tool, after a DPI-unaware PowerShell grab produced a documented false negative
(the layered Unity overlay is invisible to a DPI-virtualised `CopyFromScreen`).

Findings, all from captures taken this session:

- Avatar renderer verified live: `connected: true`, `visible: true`, `presentation_state: idle`,
  position `(3640, 2087)` on DISPLAY1; she renders standing at the taskbar, ~270 physical px tall.
  Newest physical-feedback event is `poked` at 2026-09-29T20:58Z (~40 h before this review).
- Full app (`clients/desktop_app`) and widget (`clients/desktop_widget`) captured at native physical
  resolution. Confirmed defects: raw Markdown rendered literally in both transcripts; widget header
  shows `hermes · codex` beside "Ready to talk" while the answering model is local Gemma; widget
  "Reference" label overlapped by its input; hint reads "Ctrl+E expand" while expanded; full-app
  footer stuck on a stale "Sent to SORA.".
- `GET /api/v1/companion` returns `state: "idle"` while `GET /api/v1/projections/companion` returns
  `state: "talking"` at the same instant (reproduced 3×).
- The 2026-09-30T06:19Z screen question ("What can you see on the screen currently?") was answered
  with a description of a "video editing application" that does not match the desktop, and the turn
  carries no frame reference in its persisted message.
- Neither Windows client has any voice surface; the PWA's mic uses the browser's cloud service.

## Desktop state changed during the review (disclosed)

- `SoraDesktop.exe` (pid 55372) full-app window: was **minimized**, restored and moved to (60,60).
  Nothing about the client process was restarted.
- `SoraWidget.exe` (pid 46056): **launched** — it was not running — from the built binary at
  `clients/desktop_widget/bin/Debug/net10.0-windows/SoraWidget.exe`, against the live Core with
  `--core-url http://127.0.0.1:18769`, the owner token file, and the profile's own widget settings
  file. It is a child of this agent session; the owner's `Start-SORA.ps1` path is the durable way to
  run it.
- Core, the Unity player, the Windows helpers and every other running process were left untouched.
  No task was submitted, no chat turn was sent, no grant was minted, no capture endpoint was called.

## Verified

Capture artefacts exist and were inspected: full app 1190×800, widget 1380×1050, avatar region
540×520 at the projection's coordinates. Every structural claim above was read back from the live
instance or the source at the cited `path:line`.

## Unverified / not exercised

- The plan is **not implemented**; no acceptance claim is made for any workstream in it.
- No chat turn, avatar command, desktop press/type, or capture endpoint was exercised in this session,
  so the live behaviour of those paths is unchanged and untested here.
- W2's coverage boundary is stated honestly in the plan: reads performed inside a separate agent
  process cannot be intercepted by Core today.
- The widget process started here dies with this agent session; it was not added to any launcher.
