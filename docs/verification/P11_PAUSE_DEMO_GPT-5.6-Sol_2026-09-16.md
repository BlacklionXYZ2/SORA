# P11.4 packaged Pause demonstration

- **Status:** complete
- **Completed:** 2026-09-16 19:51:55 +01:00
- **Model:** GPT-5.6 Sol

## Security and lifecycle

Core prepares a PRESS interaction only after fresh exact-target UIA revalidation under
`desktop.interact:<target-id>:press`. Preparation does not consume the grant. The grant and expected
postcondition remain in a bounded volatile Core session and are absent from the Unity command.

Unity receives only target identity/geometry, the semantic action and an opaque attempt ID. It uses
the registered `AuthorizedPressAction` and unchanged generic controller. At Contact, Unity submits
the attempt ID over the authenticated local API. Core checks device/session/expiry and unchanged
authority, then the existing P11.3 implementation consumes the grant, revalidates the control again,
claims the durable attempt and invokes the bounded UIA worker once.

Disconnect clears prepared sessions. Expired/revoked/wrong-device sessions cannot reach the effect.
The action journal remains the authority for uncertain or duplicate contact.

## Packaged acceptance

The rebuilt Unity player and owned deterministic media fixture produced the preserved evidence in
`docs/verification/p11-pause-player`.

The recorded phases are exactly:

1. `target_selected`
2. `navigate`
3. `align`
4. `reach`
5. `contact`
6. `invoke`
7. `verify`
8. `retract`
9. `completed`

The media clock advanced before interaction, then reported `paused` and remained at the same sampled
position. The accessible Pause target became Resume, Core reported `postcondition_verified`, the
fixture press count was one, and resubmitting the same attempt returned the journaled result without
resuming playback. The exact grant appears in neither the Unity command nor the evidence.

An initial packaged run failed at Reach because the standing point placed the control just outside
the avatar rig's arm envelope. The safe navigation offset was corrected and the entire packaged run
was repeated successfully; reachability was not bypassed.

## Verification summary

- Packaged interaction acceptance: **2 passed** (Pause and subsequent TYPE scenario).
- Unity 6.6 PlayMode: **19/19 passed**.
- Native desktop gate: **50 passed, 1 independently opt-in privilege test skipped**.
- Embodiment gate: **22/22 portable C#** and **35 Python passed, 3 opt-in packaged tests skipped**.
- Full repository: **273 passed, 9 explicit opt-in skips**.
- Ruff, strict mypy, generated-schema freshness and diff whitespace checks passed.

Spotify was deliberately not required or probed. It remains an optional follow-on only if its actual
supported UI/API exposes a reliable semantic target and independently observable playback state.
