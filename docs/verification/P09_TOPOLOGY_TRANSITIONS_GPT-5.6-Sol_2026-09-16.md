# P09.4 topology-transition closure — GPT-5.6 Sol

Status: **complete 2026-09-16 20:21:07 +01:00**.

This record closes P09.4 while keeping two evidence classes separate. The packaged Windows player discovered and reported the host's actual active topology. Potentially disruptive resolution, DPI, hotplug, taskbar/work-area and sleep/resume changes were exercised with deterministic layouts and unavailable/resume signals; this run did not change the user's physical display configuration or power state.

## Implemented behavior

- `TopologyTransitionTracker` classifies initial, resolution, DPI, monitor-membership, orientation, work-area and unavailable→resume transitions.
- The tracker retains the last usable topology while enumeration is unavailable. The overlay suspends once per unavailable interval instead of repeating teardown each poll, then reapplies an unchanged layout after resume.
- `AvatarLocomotion.SetTopology` retains the previous global physical-pixel anchor, cancels stale movement and relocates it into a valid work area under the new topology.
- Placement now accepts a footprint covered by the union of adjacent work areas. This permits a continuous physical seam while monitor gaps and uncovered/offscreen regions still clamp to the nearest safe work-area anchor.
- Native discovery remains one-second Win32 polling plus immediate Unity focus/resume invalidation. The earlier managed WndProc subclass remains removed.

## Actual host coverage

The rebuilt Unity 6000.6.0f1 Windows player detected:

| Surface | Actual result |
|---|---|
| Virtual desktop | `(-1280, 0)`, 5120×2160 physical pixels |
| `DISPLAY1` | primary, `(0, 0)`, 3840×2160, work area 3840×2088, DPI scale 1.5 |
| `DISPLAY6` | secondary, `(-1280, 813)`, 1280×1024, work area 1280×976, DPI scale 1.0 |
| Live behavior | topology reached Core as revision 2; movement onto the secondary monitor passed; native input, shutdown and reconnect passed |

The player SHA-256 was `718444F6A718FA668DA96EB0A58445B009673310E6129152A63DBF7A92B8DE00`.

## Synthetic transition coverage

Unity fixtures classify combined resolution/DPI changes, monitor removal, work-area changes and unavailable/resume. A relocation fixture begins on the removed offset monitor, changes to a smaller 1280×720 primary with a 1280×680 work area, and proves the resulting feet anchor and full avatar footprint are safe. Resume of an unchanged layout is still emitted and preserves the relocated position. Existing Python/Core fixtures continue to cover topology revisions, invalidation, stale-command rejection, gaps, negative origins, portrait monitors and taskbars.

## Verification

| Command / gate | Result |
|---|---|
| `scripts/build-embodiment.ps1` | Unity compile, 24/24 PlayMode tests, Windows player build passed |
| `scripts/verify-packaged-embodiment.ps1` | 1/1 packaged Core/player/native-input acceptance passed in 73.76 s |
| `scripts/verify-embodiment.ps1` | C# 22/22; embodiment 35 passed, 3 explicit opt-in skips |
| `scripts/verify.ps1` | Ruff, strict mypy over 147 source files, schemas, compileall and 273 tests passed; 9 explicit opt-in skips |

Machine-readable, non-secret evidence is in [`p09-topology-p12-grab/acceptance.json`](p09-topology-p12-grab/acceptance.json). Raw player logs and runtime data remain under ignored `.local/p09-unity-evidence`.

## Boundary

This closes the functional P09.4 acceptance and records actual current-layout integration. It does **not** claim that this run physically changed monitor resolution/scaling, unplugged hardware, moved the taskbar or suspended Windows. Those transitions are synthetic and labeled as such. P09's earlier implementation remains attributed to Gemini 3.8 Flash and GPT 6 Astra; this record covers only P09.4 closure and repairs made while beginning P12.1.
