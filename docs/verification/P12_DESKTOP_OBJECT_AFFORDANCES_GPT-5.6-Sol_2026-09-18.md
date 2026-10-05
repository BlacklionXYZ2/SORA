# P12.6 desktop-object affordances — GPT-5.6 Sol

Status: **complete 2026-09-18 08:01:57 +01:00**.

P12.6 connects Core-owned desktop-object projections to the existing embodiment command and P11 action lifecycle. It implements one reusable bridge for a deliberately small physical vocabulary; it does not implement every proposed desktop object or place object-specific branches in the Unity controller.

## Core boundary

- `DesktopObjectAffordanceRequest` binds a request ID, object ID, `look`/`point`/`touch` verb and expected canonical version.
- `DesktopObjectProjection` contains only visibility-filtered label, content, geometry and affordances. The Core-only definition is never serialized directly.
- The registry is bounded to 64 definitions by default and 256 maximum. Definitions are immutable Pydantic records.
- Visibility filtering occurs before content or capability resolution. Hidden objects are absent. Private objects require the matching owner in `LOCAL_OWNER`; local-only objects remain local; public projection cannot recover private or hidden identifiers, sentinels or affordances.
- Each advertised verb is represented as a `DESKTOP_OBJECTS` capability and selected through the existing bounded `CapabilityResolver`. The full interface is not injected when the object is irrelevant.
- Dispatch rechecks expected version, current display-topology revision and single-monitor rectangle containment. `look` and `point` require exact `DESKTOP_PRESENT`; `touch` requires exact `DESKTOP_INTERACT`. Resources are `desktop.object:<object-id>:<verb>`.
- Missing, hidden and unauthorized private objects share `not_available` and the same message, avoiding an enumeration oracle.

## Embodiment mapping

| Affordance | Existing command/lifecycle |
|---|---|
| `look` | `LOOK_AT` at the object rectangle center |
| `point` | `SHOW_MARKER` with bounded object rectangle and identity |
| `touch` | `INTERACTION_START` with registered `TOUCH`, Navigate → Align → Reach → Contact → Verify → Retract |

Unity accepts `touch` only with a target point, rectangle, object identity and interaction identity. TOUCH is registered as another `IEmbodimentActionComponent`, uses the shared controller, and receives its reach/blend parameters from `PresentationProfileRegistry`. Its semantic-effect component explicitly sets `EffectMayHaveOccurred = false`: physical presentation is not authorization or evidence of a canonical/external mutation.

## Privacy and failure evidence

- A public projection contained only the public fixture. Unique private and hidden sentinels and object IDs were absent.
- Public scope exposed no owner-only affordances. Private, hidden and missing action attempts returned the same non-enumerating failure.
- Wrong-operation grants queued no command. Post-queue revocation made delivery validation fail.
- Disconnect/no-client presentation failure returned `presentation_unavailable`; the original object definition, content and version remained byte-equivalent at the model boundary.
- The authenticated HTTP route projects registered objects and queues an affordance only when the path/body identity and exact persisted grant agree.

## Packaged acceptance

The rebuilt Windows player received three separate commands from the real Core bridge. It entered gaze for `look`, showed the object-bound marker for `point`, and completed the registered TOUCH lifecycle. Core received a `completed` event correlated to `packaged-object-touch`; the object retained canonical version 1. The full run then passed the existing native input, cross-monitor movement, drag/fall, reconnect, four-orientation ragdoll and selected-window support suites.

The Windows compositor twice returned `0xFEFEFE` for the white fixture pixel previously asserted as exactly `0xFFFFFF`. The probe now permits only channels 254–255. Window ownership, click routing and avatar hit-test requirements are unchanged, so this accommodates one color-management quantum without accepting a materially opaque or tinted overlay.

## Verification

| Gate | Result |
|---|---|
| Focused Core/API affordance tests | 4/4 passed |
| Unity 6000.6.0f1 PlayMode | 49/49 overall; P12.6 fixtures 2/2 |
| Packaged Core/player/native input | 1/1 passed in 95.27 seconds; look/point/touch and completed touch recorded |
| Portable C# / embodiment | 22/22 C#; 43 passed, 3 explicit opt-in skips |
| Repository | 281 passed, 9 explicit opt-in skips |
| Static/contracts | Ruff passed; strict mypy passed across 151 source files; schemas and compileall passed |

Machine-readable evidence is in [`p12-desktop-object-affordances/acceptance.json`](p12-desktop-object-affordances/acceptance.json). Public schemas are [`desktop-object-affordance-request.schema.json`](../../contracts/schema/v1/desktop-object-affordance-request.schema.json) and [`desktop-object-projection.schema.json`](../../contracts/schema/v1/desktop-object-projection.schema.json).

P12 is complete. P15.8 may build the canonical Kanban object on this bridge; P13.1 is the next implementation-plan item and owns higher-level event attention/debounce policy.
