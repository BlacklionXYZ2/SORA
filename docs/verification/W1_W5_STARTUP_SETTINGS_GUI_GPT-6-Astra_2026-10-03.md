# Ordinary startup / Settings / compact Voice acceptance slice

Completed **2026-10-03 08:30:46 +01:00**, contributor label **GPT-6 Astra**.
Overall status: **progress; full frontend goal remains active**.

QA root: `.local/ordinary-startup-qa-20261003` (no owner history/configuration copied; only the
earlier isolated offline-profile settings template seeded the fixture).
Primary owner Core PID52000 was not restarted. Occupied port18789 was not commandeered.

## User-side evidence and result

| Check | Fresh result | Limits |
|---|---|---|
| Root Start-SORA Core helper wiring | Actual owned Core CLI includes capture/bridge/action/type; builds validate binaries | Does not prove chat-driven press/type semantics |
| Existing selected model | Managed Gemma E2B IQ4_XS + matching explicit F16 mmproj, state ready, real GUI reply | Not another model/draft/cache combination or fresh install |
| Unified settings | Reproduced v6 projection rejection, fixed it, GUI now exposes all groups | Not every picker/value/error path |
| Settings navigation | Voice selected from menu; header/fields jump into view; one small scroll shows speed | Transient CU popup geometry required keyboard confirmation; full DPI matrix open |
| GUI Voice Save | Speed1.0→1.1 stored at revision1 and active, later revision2 preserved it | No recording/speaker-speed perceptual measurement |
| Explicit disables | Window/image/file read stayed disabled over restarts, no pending delta | Deliberate fixture choices, not owner settings; broader security audit open |
| Avatar selection | Fixture avatar false initially prevented startup; enabling fixture avatar then restarting spawned player | Fixture toggled via owner API, not CU privacy controls |
| Core restart/client sync | Final normal launcher auto-opened Widget; earlier real-model transcript restored | Owned trees force-stopped; graceful shutdown not proved |
| Real GUI model conversation | Full-app request returned exactly Startup check passed; Thinking→idle | A typed benign prompt, not microphone/complex tools |
| Compact Voice | Menu entry, Start→Loading→Ready, devices, Close→stopped; worker/child absent afterward | No microphone opened; no user-spoken turn or physical unplug |
| Close reason | Added regression; restarted Core API returns Local audio closed / microphone closed | GUI rendered the old reason before repair; new text projected by final Core |
| Ordinary companion | Player process, connected renderer, visible/idle state, topology150%/100% | Transparent window absent from CU inventory; not a visual-render acceptance |

Actual launch used:

```powershell
$env:UV_PROJECT_ENVIRONMENT='.local/frontend-verify-20261003'
./Start-SORA.ps1 -Port 18791 -StateRoot .local/ordinary-startup-qa-20261003 -Client Widget -HiddenCore
```

Earlier preparatory launches used `-NoClient`, with one initial `-NoAvatar`. Local speech
dependencies/assets were already installed; no model weights downloaded. Speech worker used the
dedicated `.local/voice-runtime` independently of Core's dependency environment.

## Preserved artifacts and checks

- `.local/ordinary-startup-qa-20261003/startup-proof.json`: captured
  **2026-10-03T08:30:15.6744783+01:00**, model ready, settingsrevision2, speed1.1 saved/active,
  avatar true saved/active, explicit read/image disables, connected/visible renderer.
- Settings JSON/recovery/last-good snapshots and benign fixture conversation retained there.
- `<QA root>/logs/llama-server.log` and `avatar-player.log` retain runtime diagnostics. Logs
  may contain private paths/prompt text; no credentials copied into this report.
- Final standard suite **576 Python passed /24 opt-in skipped**, 92.40s; **8 PWA**.
- **40 C# tests**; both client builds zero warning/error; three launcher AST parses passed.
- Previous Unity61-test evidence remains its separate earlier slice; **no fresh Unity test run**
  or rebuild claimed here because no Unity source changed.
- Cleanup checked exact own executable path, root command and parent chain before force-stop.
  Final QA ports18790/18791 no longer listening; owner Core remained; voice workers/player gone.

## GUI criticisms and next acceptance

The Settings version mismatch was a functionality blocker, not a cosmetic issue, and is fixed.
Section navigation addresses controls buried several screens deep. Long labels now have full-name
tooltips, but advanced controls still need a broader layout review. Device keys are usable but a
real enumerated device chooser would be easier than copying names. Full-app header model name is
visually ellipsized at narrow width; canonical accessible status remains available. Voice and chat
currently use different visual styling; accessibility/mixed-DPI review is not complete.

Next scope remains the complete planned frontend: agent/model/tool catalogue and delegation
controls, native/visual interaction schema and outcome verification, other W1/W4/W6/memory gates.
W5 still needs human-spoken real GUI/audio/mouth, barge-in and physical device unplug/recovery.
This slice does not require the owner to intervene before development can continue on those other
unfinished implementation items.
