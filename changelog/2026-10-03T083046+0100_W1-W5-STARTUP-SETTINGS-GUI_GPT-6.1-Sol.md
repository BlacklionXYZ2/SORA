# W1/W5 startup and Settings GUI repair

Contributor label: GPT-6.1 Sol
Slice completed: **2026-10-03 08:30:46 +01:00** (Europe/London).
Status: **implemented and verified for the bounded slice**; overall frontend goal remains active.

## Implemented

- `scripts/start-manual-test.ps1`, the Core entry used by root `Start-SORA.ps1`, now builds,
  validates and wires both press/type helpers alongside capture/native observation. Previously
  these were only wired by the separate full launcher. Saved static policy still controls use.
- Root launcher adds `-NoClient` and `-HiddenCore` for supervised testing. Normal interactive
  launch/console behavior is unchanged. Hidden launches print their owned launcher PID and
  require their supervisor to stop them; these switches are not a new tray shutdown feature.
- Full launch readiness now also requires a freshly written token file, matching the root
  launcher's protection against stale-token startup checks.
- Repaired Windows `FullAppProjection` settings-version recognition: Core v6 was incorrectly
  dropped, making a newly built GUI display the old LM Studio settings instead of all unified
  access, perception, model and Voice controls. Added v6 regression assertions.
- Added Settings section navigation. Selecting a group puts its heading at the top rather
  than barely visible at the bottom. Label tooltips include the full label and key. Save
  preserves the selected group instead of resetting its name while retaining the old scroll.
- Explicit audio close now says “Local audio closed. The microphone is closed.” rather than
  falsely saying access/settings changed. Real policy invalidation retains its own reason.
  Added a close-versus-policy regression test.
- Updated Settings/tryout/Voice guidance, current store version, evidence and scope tracker.

## Fresh verification

- `scripts/verify.ps1` using dedicated `.local/frontend-verify-20261003`: **576 passed,
  24 opt-in skipped**, 92.40 seconds; Ruff, mypy (238 source files), compile/contracts checks
  and **8 PWA checks** passed.
- `dotnet test clients/csharp_tests/csharp_tests.csproj`: **40 passed**. Both Windows clients
  build with **zero warnings/errors**; final full-app source rebuilt and tested.
- All three edited launcher scripts pass PowerShell AST parsing. `git diff --check` passed
  (existing LF/CRLF notices only). Launcher source assertions cover native helper build/wiring;
  these assertions alone are not native-action acceptance.
- Isolated root launches on Core **18791**, managed model **18790**, real Gemma 4 E2B IQ4_XS
  and explicit adjacent F16 projector. First requested Core port18789 was occupied; launcher
  refused it, and no unknown listener was stopped. Source/actual Core CLI confirms all four
  helper paths. Existing owner Core PID52000 remained alive, untouched.
- Computer Use reproduced the legacy Settings regression, then reviewed the repaired unified
  page, section menu, Voice fields, and actual GUI Save of speech speed **1.0 → 1.1**.
  JSON/projection proves saved and active 1.1 on subsequent starts; explicit window/image/file
  disables remained false. Avatar was enabled only in the isolated fixture via its owner API.
- Final root launch **without `-NoClient`**, with `-Client Widget -HiddenCore`, automatically
  opened the compact client. Its restored transcript showed the earlier real-model GUI answer
  **Startup check passed**. Full-app prompt/answer and idle recovery were reviewed through CU.
- Compact menu → Local voice → Start reached Ready using actual owned Python worker
  (launcher17952/worker20268 during that run), with microphone closed and device list populated.
  GUI Close audio reaped both handles. No microphone capture occurred in this slice.
- Ordinary startup spawned packaged Unity player; renderer projection connected/reported visible,
  idle and fresh two-monitor topology (150%/100%). Computer Use did not expose its transparent
  window, so **no fresh visual avatar review** is claimed. No Unity sources were changed here.
- Corrected Close audio text was checked against the restarted Core API after the source repair.
- Final owned GUI/Core/model/avatar process trees were stopped with verified ancestry/path checks;
  no QA worker/player/listener remained. Fixture/evidence preserved, not deleted.

## Boundary and remaining work

Restarts used controlled **forced termination of owned QA trees**, followed by the ordinary
launcher; this proves restart persistence, not graceful Ctrl+C/tray shutdown acceptance. The
root launch used an existing dependency environment and model weights, not fresh installation.
The separate full launcher was parsed/source-checked, not launched in this slice.

No full W1/W5/W6 closure: still require broad caller/native-action audits, user-spoken GUI → child
worker → real model → actual audio/mouth, physical device loss/recovery, complete DPI/layout
matrix, custom owner VRM visual acceptance, and all remaining model/catalogue/delegation/tool
requirements. Current helper wiring and model reply do not prove arbitrary desktop interaction.

Detailed evidence: [verification](../docs/verification/W1_W5_STARTUP_SETTINGS_GUI_GPT-6-Astra_2026-10-03.md).
