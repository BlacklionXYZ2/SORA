# How to use: ARDY's steady long idles and getting up after a fall

Model name: **Opus 5.5**. Checkpoint **2026-10-30 08:52 UTC**. Status: **documented**.

The change itself is in motion-lab's `ardy-runtime` (the service SORA's Reload motion model
starts), logged in motion-lab's changelog as
`2026-10-30T085000+0000_ARDY-STRESS-IDLE-ANCHOR-AND-GET-UP_Opus-5.5.md`. In short:

- **Long idles:** a stress test found that 2 minutes of idling under ARDY came apart. Every
  variant tried drifted within 30 to 60 s into flailing, spinning (8,520° in total) and floating
  or collapsing hips. ARDY is now held near her own standing pose once she has stood still for
  1.6 s. Over 2 minutes, outside the data's joint limits went from 29% to 3.3% and the head
  below the hips from 18% to 0.
- **Getting up:** after a fall, ARDY used to leave her on the ground (hips 0.1 to 0.45 m). It now
  gets her up within about 2.5 s, from a real lying pose under "get up" and under idle (6 of 6
  runs).

## Changes in SORA

- `HOW_TO_USE.md`: a short entry under Motion, and the "Last updated" line.

No SORA code changed: Core passes no new arguments, and the new behaviour is the service's
default (`--no-anchor` turns it off). A running SORA picks it up at its next Reload motion
model. The owner's running SORA was not touched.

## Verification

- Component and live-model evidence in motion-lab (`ardy-runtime/outputs/stress-service-fp16-s4-final.json`):
  - `test_service.py` passes, including real-time pacing;
  - every other stress scenario is unchanged.
- **Not run:** her built player with Core and ARDY on screen; the owner's judgement of the
  get-up.

Nothing committed.
