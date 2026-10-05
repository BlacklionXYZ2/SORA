# ADR 0011: Private Paired Remote Transport

- Status: implemented; in review pending physical-phone acceptance
- Date: 2026-09-22
- Implemented: 2026-09-22 13:43:41 +01:00
- Model: GPT-5.6 Sol

## Context

P15.1 intentionally kept SORA's owner bearer and browser application on loopback. P15.2 needs a
phone-compatible path without turning private-network membership into authority, transmitting the
owner credential to a mobile device, weakening P08's ban on URL credentials, or creating a public
development endpoint.

## Decision

SORA uses two listeners with different trust domains:

1. The owner listener remains loopback-only HTTP and retains the existing bearer credential. It is
   the only listener that can create pairing invitations, list/revoke paired devices and inspect the
   remote audit.
2. Remote access is disabled by default. Enabling it creates a separate TLS-only listener on one
   concrete loopback, private, link-local or overlay IP. Configuration requires a certificate,
   private key and at least one exact HTTPS browser origin. Unspecified, multicast, reserved, global
   and wildcard hosts are rejected.
3. The owner bearer is never accepted remotely. A short-lived one-time invitation produces a
   device-bound high-entropy credential. That credential can mint short-lived `SoraSession`
   credentials whose scopes must be a subset of the device's persisted scopes. Only hashes are
   stored by Core.
4. Remote state routes are an exact semantic allowlist. Unknown routes and sensitive settings,
   extension, object and action surfaces are structurally absent. Task control is excluded from the
   default remote scopes. Remote event replay contains ordering/invalidation metadata only; the
   client refreshes authorized projections separately.
5. Revoking a device atomically revokes every active session. Authentication rechecks session
   expiry and device/session revocation on each request. Pair claims are transactionally one-use.
6. Pair/session attempts and total requests use independent per-source sliding-window limits. A
   bounded owner-only audit contains sanitized identifiers, route, outcome and non-secret details.
7. Browser pairing persists only the paired-device credential in origin-scoped IndexedDB. The owner
   bearer and short session tokens remain in memory, are sent only in authorization headers and are
   excluded from URLs, service-worker storage and response caches.
8. Remote WebSocket upgrades are not supported because browser JavaScript cannot set the required
   authorization header. The authenticated bounded HTTP replay introduced by P15.1 remains the
   browser transport rather than putting credentials in a URL or cookie.

## Consequences

- Possessing network access to the listener is insufficient to read or control SORA.
- Certificate issuance, host-name resolution, firewall policy and private-network/overlay setup stay
  explicit operator responsibilities; SORA does not expose or provision a public tunnel.
- A compromised browser profile can recover the persisted paired-device credential. The user can
  revoke that device locally; the credential cannot authorize routes outside its paired scopes and
  cannot replace the owner bearer.
- Rate counters are deliberately in-memory and reset on Core restart. Pairing, device, session,
  revocation and audit state persist in SQLite.
- The repository includes a self-signed certificate solely for deterministic automated TLS tests.
  It must never be used for an installed or live SORA instance.

## Verification status

Deterministic TLS/API/PWA tests prove one-use concurrent pairing, short-session expiry and renewal,
scope non-escalation, route denial, owner-bearer rejection, exact origin/Host checks, plaintext
failure, revocation, restart persistence, rate limiting, audit redaction and packaged PWA assets.
The acceptance clause that a real paired phone connects through a device-trusted certificate has not
yet been run, so P15.2 remains in review.

## Reversal

Remote access can be disabled without changing the owner listener or deleting paired-device records.
Removing the second listener leaves the P15.1 loopback PWA and P08 API behavior intact. A later
transport can retain the same pairing/session/scope manager if it preserves these trust boundaries.
