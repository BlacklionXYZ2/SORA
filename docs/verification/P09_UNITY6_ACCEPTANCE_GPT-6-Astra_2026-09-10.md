# P09 Unity 6 packaged acceptance — GPT 6 Astra

Status: **implemented and in review; P09.4 physical transition acceptance remains open.** This continuation replaces the earlier missing-editor limitation with actual Unity compilation, rendering and native-input evidence. It preserves the original Gemini implementation and the preceding repair/implementation records.

The user-installed editor is `C:\Program Files\Unity\Hub\Editor\6000.6.0f1\Editor\Unity.exe`, version **6000.6.0f1 (f7f8ed4d1e24)**. The Windows x64 development player uses Mono/.NET Standard 2.1, the built-in pipeline, Direct3D 11 and the BitBlt swap chain. The project now pins **UniVRM 0.131.2** with a resolved package lock. UniVRM 0.128.0 failed against Unity 6 removed APIs; the upgraded release supplies the compatible package layout and API changes. Unity-generated project settings and migration dependencies are retained. The generated Multiplayer Center package is editor migration output, not a SORA multiplayer feature.

## Acceptance evidence

The reproducible commands are `scripts/build-embodiment.ps1`, `scripts/verify-embodiment.ps1` and `scripts/verify-packaged-embodiment.ps1`. The last command launches a temporary isolated Core and two successive instances of the real packaged player. The input fixture is a separate owned WinForms process. Credentials are ephemeral environment values; normal Core state is untouched. No external reasoning provider is called.

| Plan item | Result and scope |
|---|---|
| P09.1 | Windows build succeeds; the licensed Seed-san humanoid loads and renders. A known white fixture pixel remains white through the composed overlay. Native styles are topmost/layered/noactivate. Blank-space clicks reach the fixture; avatar clicks resolve to the player and do not reach the fixture. |
| P09.2 | Actual Core/player transport reports idle, left/right arrival, gaze and marker state. The avatar moves onto the secondary negative-x display and returns. Graceful player close exits zero, leaves Core serving, and removes the live embodiment. Reconnection is idle and does not replay the old destination. |
| P09.3 | Existing Python/C# coordinate, work-area, portrait, gap and mixed-DPI fixtures remain passing. Unity camera projection tests pass. Actual viewport and rendered feet-anchor checks are within one physical pixel. |
| P09.4 | Current Win32 monitor/work-area/DPI enumeration and actual multi-monitor movement pass. Synthetic topology invalidation and safe relocation tests pass. **Physical resolution/DPI changes, unplug/replug, taskbar relocation and sleep/resume were not exercised.** |
| P09.5 | Own-camera PNG shows the recognizable avatar and independent cyan target rectangle. HUD exposes screen/world/navigation/gaze/reach-plane diagnostics. Actual viewport/anchor alignment and bounded frame timing are recorded below. IK solving remains P11. |
| P09.6 | Real command transport exposes target identity, displays the marker, expires it and clears it on idle. Unity PlayMode verifies the semantic reach event without an animation asset; existing transport tests cover the other hooks. The product marker does not inject input or establish an OS effect. |

The current native desktop is **5120×2160 at (-1280, 0)**. Primary DISPLAY1 is 3840×2160 at (0,0), DPI scale 1.5, work area 3840×2088. Secondary DISPLAY6 is 1280×1024 at (-1280,813), DPI scale 1.0, work area 1280×976. The packaged test reaches the secondary anchor (-640,1689) and returns to (1280,1988). That final global anchor projects to client (2560,1988), exactly accounting for the virtual desktop's -1280 left edge. Portrait displays and changed layouts are synthetic coverage only.

## Repairs discovered by running Unity

- Upgraded UniVRM and its Git package paths for actual Unity 6 compilation; updated editor build-target APIs and pinned generated project settings/package resolution.
- Fixed an observed 5098×2104 client viewport when the desktop required 5120×2160. Unity had reintroduced nonclient borders during resolution changes. Reasserting popup/visible style before native bounds application removes the 22×56 error.
- Removed the managed WndProc subclass after reproducible player shutdown access violations (0xC0000005). Per-frame collider-based transparent hit testing remains; topology discovery uses one-second polling and Unity focus/resume callbacks. Subsequent packaged close/reconnect checks exit zero.
- Added validated `SORA_CORE_PORT` for isolated local Core tests. Mismatched native/Core snapshots stop movement, gaze and marker presentation until reconciliation.
- Replaced UniVRM's global spring-bone service with its supported per-avatar standalone runtime. Allocation stack traces identified two persistent tail-backup arrays created during global-service removal after avatar disposal. All four PlayMode tests now pass without a `Leak Detected` report, with stack tracing enabled. Spring simulation remains enabled. No package-cache source was edited.
- Guarded metrics writing against Unity's unspecified object destruction order, preserving the last complete periodic sample when camera/motion/marker objects are already destroyed. Packaged acceptance rejects exception or native-leak reports in either player log.
- Added own-camera capture, a separate native input fixture and executable packaged acceptance. The build harness now fails on native leak reports as well as compilation, activation and process failures.

## Measured and archived results

Final packaged acceptance completed **2026-09-10 08:18:15 +01:00** in **73.47 seconds**. Evidence was archived at **08:18:32 +01:00**. The final 3,587-frame sample measured mean **16.7321 ms**, p50 **16.6674 ms**, p95 **16.6761 ms**; latest CPU frame **16.6929 ms** and GPU frame **0.02744 ms**. This supports an approximately 60 FPS baseline on this host within the measurement scope below.

Machine-readable final results, exact UTC times, player SHA-256, frame measurements and source identities are stored in [the evidence manifest](p09-unity6/evidence-manifest.json). The archived files are [PlayMode XML](p09-unity6/playmode-results.xml), [player acceptance](p09-unity6/player-acceptance.json), [native input acceptance](p09-unity6/native-input-acceptance.json), [presentation metrics](p09-unity6/presentation-metrics.json) and [own-camera image](p09-unity6/own-camera.png).

The full Python suite passed **214 tests**, with **one deliberately skipped opt-in packaged test**. That packaged test was then run separately against the built executable and passed. Portable C# tests passed **21/21**; Unity PlayMode passed **4/4**. Ruff, strict mypy over **119 source files**, published-schema freshness and Python compilation passed. Fixture build had zero warnings/errors. Unity source still emits nullable-context/unused-platform-field warnings; this record does not claim a warning-free Unity build.

Frame measurements exclude five seconds of warmup and retain at most 3600 samples. They are a short development-player baseline containing movement/marker activity followed by predominantly idle frames, not separate controlled idle and movement benchmarks. CPU/GPU figures are Unity frame timing samples, not utilization percentages. No memory budget, long-duration stability, cross-machine performance or release-build performance is claimed. The manifest records the final measured values rather than conflating them with earlier runs.

The metrics producer deliberately leaves `visual_alignment_verified` and `cross_process_click_through_verified` false: it cannot attest to its own rendering or native routing. Separate test assertions check viewport/anchor error, and the native input result records cross-process routing and composed transparency. The PNG is captured from SORA's own camera only; it contains no desktop/application screenshot. Raw Unity logs and temporary runtime data stay under ignored `.local/p09-unity-evidence` rather than publishing licensing/session data.

## Remaining P09 closure

On the packaged player, perform each physical resolution/DPI, display disconnect/reconnect and sleep/resume transition. Record before/after native layout and Core revision, interrupt an active destination/marker, confirm the stale presentation stops, and verify the visible avatar relocates into a valid work area. Include a taskbar-edge change. Restore the user's original display settings after each test. Current polling/reconciliation code and synthetic tests are implementation evidence, not proof of these host transitions.

P09.1/.2/.3/.5/.6 are accepted at the scope above. **P09.4 and the overall phase DoD remain open.** This player is a development acceptance build with a licensed verification character, not SORA's final character or a signed release installer.

See the [GPT 6 Astra continuation changelog](../../changelog/2026-09-10T080450+0100_P09-UNITY6_GPT-6-Astra.md) and [earlier source implementation record](P09_IMPLEMENTATION_GPT-6-Astra_2026-09-09.md) for the complete attribution chain.
