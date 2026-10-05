# SORA owner manual-verification checklist — 2026-09-23

This is a handoff of **checks that require your device, physical setup, or subjective judgement**.
It does not reopen completed deterministic stages or assert that the checks below have passed.
Use isolated/test content first. Never put bearer tokens, pairing codes, grants, private
conversation contents or API keys in screenshots or shared logs.

## Open acceptance gates

| Stage | What you need to check | Evidence to report | Why it remains open |
|---|---|---|---|
| P15.2 private remote transport | On your actual phone, trust a deliberately provisioned certificate through the normal OS/browser trust flow, pair once on your private network, read allowed state, reconnect, revoke, then confirm the old credential fails. Do not bypass an HTTPS warning or expose a public listener. | Phone/browser/OS, certificate trust method, paired/reconnect/revoked outcomes, redacted screenshots. | Same-host TLS fixtures passed, but no physical phone with trusted certificate was exercised. |
| P15.7 full app | With widget, full app, PWA and avatar connected to one isolated Core, save one safe dialogue/worker/context setting in the full app, restart Core, then create one dialogue turn and specialist task; compare task ID/status and conversation after another restart/reconnect. Inspect which remaining §4.12 settings you expect to change in-app versus at validated Core startup. | Connected native save/pending/active result, four-surface state comparison and the settings choice, with secrets hidden. | A real Core HTTP restart test passed, but connected native saving, simultaneous rendered parity and broader validated settings editing are not yet accepted. |

## Useful real-world coverage after the personal desktop release works

| Earlier stage | Suggested manual check | Existing boundary |
|---|---|---|
| P15.1 PWA | Open/install the PWA in your normal browser, test narrow-window layout, keyboard access, offline indication and convergence after reconnect, and the visible browser-microphone notice before granting any mic permission. | Browser code and replay/cache tests passed; no physical microphone test was claimed. |
| P14.2–P14.5 voice | With a microphone and speakers/headphones you choose, assess listening, interruption/barge-in, mouth/audio timing, device disconnect and echo/noise in a normal room. | The end-to-end client used deterministic audio adapters; physical microphone-to-silence and acoustic quality were not measured. |
| P09.4 display transitions | If convenient and safe, test a real DPI/resolution change, monitor disconnect/reconnect, taskbar work-area change and sleep/resume with the packaged avatar. First save your current display layout and close sensitive work. | Current two-monitor topology and synthetic transition matrix passed; disruptive physical transitions were deliberately not performed. This is stronger hardware coverage, not an unrecorded P09.4 failure. |
| P15.4 native input/drag-fall | Re-run the opt-in fixture only with the intended test window unobscured, then observe raw cross-process input and simple drag/fall. Do not test against another person's app or an elevated/sensitive window. | The integrated fixture's ownership check refused an obscured primary-window probe, so that sub-check was `not_run`; the separate authorized UIA Pause scenario passed. |
| P15.5 avatar feel, later P15.12 polish | Judge wave, sit, lean, visual climb, run/gaze, quiet mode and distraction on your actual desktop. Note clipping, uncanny timing and what deserves hand-authored animation. | Deterministic Unity/C# behavior passed; visual sit/climb is not proof of seat contact or physical traversal. Blender is optional for later authored clips, not a requirement for current semantics. |

The personal desktop release gate in the [implementation plan](../../SORA_IMPLEMENTATION_PLAN.md)
is P15.6–P15.8; P15.2 is independent if private phone access is included. P15.9
social integration, P15.10 public extension management, P15.11 public harness SDK
and P15.12 polish do not block that personal release. The unsigned package and
provider/model distribution choices remain product-release policy rather than
something this checklist silently accepts.

Source records: [P15.2](P15_PRIVATE_REMOTE_TRANSPORT_GPT-5.6-Sol_2026-09-22.md),
[P15.7](P15_FULL_APPLICATION_GPT-6_2026-09-23.md),
[P09.4](P09_TOPOLOGY_TRANSITIONS_GPT-5.6-Sol_2026-09-16.md),
[P14.2](P14_STREAMING_VOICE_SESSIONS_GPT-5.6-Sol_2026-09-19.md),
[P14.3](P14_BARGE_IN_GPT-5.6-Sol_2026-09-19.md),
[P15.4](P15_INTEGRATED_USER_SCENARIOS_GPT-5.6-Sol_2026-09-22.md),
[P15.5](P15_ADVANCED_BEHAVIOR_GPT-6_2026-09-22.md).
