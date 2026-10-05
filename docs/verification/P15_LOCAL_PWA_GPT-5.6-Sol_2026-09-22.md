# P15.1 responsive local PWA — GPT-5.6 Sol

Status: **complete 2026-09-22 11:02:02 +01:00**.

P15.1 provides an installable, conversation-first browser client on the existing authenticated local
Core boundary. It deliberately does not create remote access, pairing or a public development
endpoint; those authority and transport changes remain P15.2.

## Client surface

Core serves a build-free application shell from a fixed packaged allowlist. The PWA includes:

- canonical conversation history and one-turn direct dialogue;
- responsive phone/desktop layouts, keyboard navigation, focus visibility and reduced-motion rules;
- provider availability plus canonical task status;
- explicit task steering and cancellation for non-terminal runs;
- an optional trace that contains event type, sequence and time only, never envelope payloads or
  private reasoning;
- an install prompt, standalone manifest and generated 192/512 PNG icons; and
- an explicitly labelled browser speech-recognition control.

The browser microphone is a UI seam, not a replacement for P14's local audio pipeline. Its visible
notice says browser speech recognition may be remote. No microphone permission was requested during
this verification and no physical audio test is claimed.

## Authentication and cache boundary

The app shell is public only on the loopback-bound Core server and contains no user state or token.
The user supplies Core's bearer token after navigation. `SoraApiClient` keeps it in a private field
for the page lifetime and sends it only in the `Authorization` header; it does not use query strings,
cookies, `localStorage`, `sessionStorage` or IndexedDB.

Every client fetch uses `cache: no-store`, omits credentials/cookies and suppresses referrer data.
Core marks authenticated API responses with `Cache-Control: no-store`, `Pragma: no-cache` and
`Vary: Authorization, Origin`.

The service worker's cache is an exact immutable list containing only the app shell, modules,
manifest and icons. Requests under `/api/`, `/healthz` and `/readyz` always go directly to `fetch`
with `cache: no-store`; there is no cached fallback for them and no dynamic `cache.put` path.
Navigation can fall back to the cached shell while all private content remains unavailable offline.

Static requests use an exact route-to-file map rather than filesystem path joining. Unknown or
traversal-like paths do not become public assets and proceed through ordinary bearer authentication.
Existing host and origin checks run before both app-shell and API dispatch.

## Browser-compatible reconnect

The existing WebSocket requires an `Authorization` header. Browser JavaScript cannot attach that
header, and a credential query parameter is intentionally rejected by P08. P15.1 therefore adds
`GET /api/v1/events?since_sequence=<n>&limit=<n>` as a bounded authenticated replay path instead of
weakening the transport boundary.

The route:

- accepts only non-negative cursors and pages of 1–500 events;
- reads only the current owner's durable stream;
- returns monotonic replay pages and an explicit `more_available` flag;
- detects retained-history expiry, empty/interior replay gaps and cursors ahead of Core; and
- supplies an authoritative state snapshot when replay cannot safely continue.

The browser coordinator retains a high-water sequence only in memory. On initial connect,
reconnect, any new event or resync requirement, it refreshes canonical messages, tasks, companion,
capabilities and provider/status projections. A deterministic two-client fixture disconnects one
store while canonical messages and task status change, delivers the missing events one item per
page, and proves both stores converge to identical authoritative projections at sequence 4. A live
Core fixture also exercises missed dialogue events, paginated replay and future-cursor resync.

## Verification

| Gate | Result |
|---|---|
| PWA live Core/API | 2 passed |
| Browser runtime/unit | 5 passed |
| Repository | 329 passed, 10 explicit opt-in native/Unity skips |
| Static/contracts | Ruff passed; strict mypy passed across 176 source files; schemas fresh; compileall passed |
| Assets | JavaScript syntax and deterministic PNG regeneration checks passed |

Machine-readable acceptance: [`p15-pwa/acceptance.json`](p15-pwa/acceptance.json).

The full repeatable gate is `./scripts/verify.ps1`; the zero-dependency browser subset is
`./scripts/verify-pwa.ps1`.

## Limits

- The host exposed no controllable browser surface during the final visual-QA attempt. Responsive
  CSS, semantic controls, manifest data and JavaScript behavior are tested, but no rendered-layout,
  install-banner or specific-browser compatibility claim is made.
- Browser speech recognition may use a browser vendor service. Use P14's client-local pipeline when
local VAD/STT/TTS is required.

Canonical message reads order equal-timestamp records by durable SQLite insertion order rather than
random message UUID. This preserves user-then-assistant order for direct dialogue and atomic voice
turns without changing the stored timestamps.
- The token is re-entered after reload by design. Device pairing, revocation and scoped remote
  sessions are P15.2 work.
- Service-worker offline support covers only the non-sensitive shell. Conversation, tasks,
  projections and traces intentionally fail closed without Core.

Roadmap after P15.1: **79/91 checklist items (86.8%)**. P15.2 is next. No commit, tag or staging
operation was performed.
