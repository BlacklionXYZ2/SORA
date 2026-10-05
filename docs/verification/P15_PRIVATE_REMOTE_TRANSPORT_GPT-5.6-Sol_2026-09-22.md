# P15.2 private paired remote transport — GPT-5.6 Sol

Status: **implemented/in review 2026-09-22 13:43:41 +01:00**.

P15.2's deterministic implementation is complete, but its acceptance criterion explicitly names a
paired phone. No physical phone or device-trusted production certificate was available during this
run, so this report does not mark P15.2 complete.

## Implemented boundary

- The existing owner HTTP listener is permanently loopback-only. A separately enabled second
  listener requires TLS, one concrete non-public address and exact HTTPS origins/hosts.
- The owner bearer is rejected on the remote listener. The remote listener accepts only one-time
  pairing claims, device-authenticated session creation, public liveness and exact scoped routes.
- Invitation, device and session secrets are high entropy. Core persists SHA-256 hashes rather than
  reusable secret material. Invitation claim and device/session revocation are atomic SQLite writes.
- Sessions expire after a configurable 60–3,600 seconds and cannot exceed the device's paired
  scopes. Default scopes permit conversation, read-only tasks, events and safe projections; task
  creation/steer/cancel requires an explicitly paired `tasks:control` scope.
- Unknown routes, settings, extensions, desktop objects, native actions and remote WebSocket
  upgrades are denied. Remote replay strips envelope payloads and authoritative snapshots.
- Per-source request and pairing/session limits are enforced. A bounded owner-only audit omits
  invitation codes, device credentials and session tokens.
- The PWA now supports owner invitation/device/revoke controls and remote HTTPS pairing/reconnect.
  IndexedDB retains only the paired-device credential for that exact origin. The owner bearer and
  short-lived session token remain memory-only and every authenticated request is network-only.

## Acceptance matrix

| Requirement | Evidence | Status |
|---|---|---|
| Paired device connects | Real TLS listener plus browser-compatible client fixture claims once, creates a scoped session and reads canonical state | Deterministically verified; physical phone pending |
| Revoked device fails | Local owner revocation marks device and all sessions revoked; subsequent request fails; state survives restart | Verified |
| Unpaired/network-only client fails | Unauthenticated remote state, leaked owner bearer and wrong device/session are rejected | Verified |
| Encrypted browser transport | Remote listener is constructed with TLS 1.2 minimum; plaintext HTTP to its port fails | Verified |
| Scoped sessions | Read-only and explicit task-control devices exercise allowed operations while dialogue/settings/extensions/escalation fail | Verified |
| Rate limits and audit | Pairing limit returns 429; audit records allowed/denied actions and contains none of the test secrets | Verified |
| No public development endpoint | Disabled by default; global/unspecified/wildcard configuration rejected; owner listener cannot leave loopback | Verified by configuration tests |
| Actual phone and trusted certificate | No physical phone/browser certificate-trust run was available | Not run; completion blocker |

## Verification

`./scripts/verify.ps1` passed on Windows/Python 3.12.10:

- repository: **334 passed, 10 explicit opt-in native/Unity skips**;
- Ruff: passed;
- strict mypy: passed across **178 source files**;
- exported contract schemas: fresh;
- compileall: passed; and
- PWA JavaScript/icon gate: **7 passed**.

Focused verification:

- `pytest tests/api/test_remote_access.py tests/api/test_pwa.py tests/persistence/test_database.py -q`:
  **9 passed**;
- P08 local plus P15.2 security regression: **11 passed**; and
- wheel inspection confirmed `sora/pwa/app.js`, `sora/pwa/device-vault.js` and
  `sora/pwa/index.html` are packaged.

A live-process host smoke bound the TLS listener to this machine's active Ethernet address,
`192.168.1.185/24`, reached `/healthz` over TLS and confirmed an unpaired `/api/v1/messages` request
was denied. The test client disabled certificate verification because it used the repository's
localhost-only test certificate; this proves non-loopback bind/routing and authorization behavior,
not phone certificate trust.

The automated TLS fixture uses `tests/fixtures/tls/localhost-test-cert.pem` with certificate
verification disabled only inside the test client. It is test evidence for encrypted framing and
listener policy, not a production trust claim.

Machine-readable acceptance: [`p15-private-remote/acceptance.json`](p15-private-remote/acceptance.json).

## Remaining acceptance work

Install or provision a certificate trusted by the intended phone, bind SORA to its actual private or
overlay address, open the remote `/app`, claim a fresh local-owner invitation, exercise conversation
and reconnect, revoke the device locally, and confirm both the existing and newly requested session
fail. Record the phone/browser/network/certificate environment without storing credentials.

Roadmap remains **79/91 checklist items (86.8%)**. No commit, tag or staging operation was performed.
