# P11.5 logical TYPE verification

- **Status:** complete
- **Completed:** 2026-09-16 19:52:33 +01:00
- **Model:** GPT-5.6 Sol

## Action boundary

`AuthorizedTypeAction` is a separately registered Unity component with action ID `type`. It claims
the same locomotion/gaze/reach presentation controllers as PRESS and runs through the unchanged
generic lifecycle. The generic controller contains no TYPE branch, and the POINT/PRESS components do
not enumerate or delegate to TYPE.

The public request defines one exact semantic replacement. Core binds it to one volatile desktop
target and an exact persisted `desktop.interact:<target-id>:type` grant. Text and grant remain in a
volatile prepared session until Contact. Unity receives neither value. At Contact, Core rechecks
session/device/expiry/authority and the target's process, runtime identity, geometry, name, enabled
state and topology before consuming the grant and claiming a durable attempt.

The dedicated native worker supports only UIA `ValuePattern.SetValue`. It rejects inaccessible,
elevated, ambiguous, moved, disabled, offscreen, password, read-only or unsupported controls and
verifies the resulting ValuePattern value after one call. There is no keyboard injection fallback.

## Recovery and privacy

Attempt reservation precedes native execution. Conflicting attempt reuse fails; identical reuse
returns the journaled result. Cancellation/transport failure after the execution claim becomes an
explicit non-replayed `unknown_outcome`. A fixture sentinel proved the typed value is absent from the
SQLite database. It is also absent from Unity commands and interaction evidence.

Password UIA nodes are rejected while selecting a target and again by the native worker. This stage
therefore demonstrates only a permitted ordinary fixture field, not credentials or command input.

## Packaged acceptance

`docs/verification/p11-type-player/acceptance.json` records:

- target selection followed by navigate, align, reach, contact, invoke, verify, retract, completed;
- terminal status `completed`, reason `postcondition_verified`;
- an independently verified exact text value in the owned WinForms fixture;
- no text or grant in Unity evidence;
- no additional text mutation when the attempt is resubmitted.

## Verification summary

- Packaged interaction acceptance: **2 passed** (Pause and TYPE).
- Unity 6.6 PlayMode: **19/19 passed**, including completed/failed/unknown TYPE outcomes.
- Native desktop gate: **50 passed, 1 independently opt-in privilege test skipped**.
- Embodiment gate: **22/22 portable C#** and **35 Python passed, 3 opt-in packaged tests skipped**.
- Full repository: **273 passed, 9 explicit opt-in skips**.
- Ruff, strict mypy, generated-schema freshness and diff whitespace checks passed.
