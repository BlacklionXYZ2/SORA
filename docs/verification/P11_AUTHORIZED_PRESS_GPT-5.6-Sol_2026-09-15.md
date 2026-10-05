# P11.3 authorized PRESS verification

- **Stage:** P11.3 — registered authorized Level 3 action
- **Status:** complete
- **Completed:** 2026-09-15 13:53:17 +01:00
- **Model:** GPT-5.6 Sol

## Acceptance result

P11.3 satisfies its implementation-plan acceptance criteria. `AuthorizedPressAction` is an
independently registered Unity component using the unchanged P11.2 lifecycle. At semantic contact it
calls Core through `IDesktopPressTransport`; Core exclusively owns persisted authorization,
contact-time target revalidation, grant consumption, the native effect journal and independent
postcondition verification.

The implemented Level 3 resource is exactly
`desktop.interact:<desktop-target-id>:press`. A short-lived P10 target remains identity only and does
not authorize action. Before invoking, Core re-observes the target under this distinct operation,
checks process identity/topology/enabled state/name/rectangle, consumes the bounded grant, verifies
that authority did not change in flight, and compares the fresh contact target with the geometry used
for reaching.

## Native effect boundary

`clients/windows_action` is a separately configured, killable .NET 10 worker. It accepts only
`press`, never a command or executable from the request. It rechecks the PID/start time, owned root
window, exact runtime/native/automation/control identity, enabled/offscreen state, accessible name and
physical rectangle. It refuses elevated targets and unsupported controls. Only then does it call UIA
`InvokePattern.Invoke` once. It verifies a changed accessible-name postcondition after the invocation;
neither avatar animation nor the return from `Invoke` is sufficient evidence.

The owned WinForms fixture changes `Confirm fixture` to `Confirmed once` and persists a press count.
Native acceptance observed one real invocation, verified the changed accessible name, repeated the
same contact request, and confirmed the fixture count remained exactly one.

## Persistent crash/no-replay boundary

SQLite schema migration 5 adds `desktop_action_attempts`. Core atomically reserves an attempt before
authorization work and transitions it to `executing` before launching the native helper. Identical
attempt IDs return the existing record without another grant use or effect. Conflicting reuse is
rejected. Startup recovery converts an unfinished `executing` record to `unknown_outcome` and never
replays it. Worker timeout, cancellation or lost/malformed output after the execution claim are also
unknown. Confirmed no-effect failures remain `failed`; only the observed postcondition becomes
`completed` with `verified=true`.

Fixtures cover:

- exact Level 3 grant consumption and rejection of an expired grant;
- movement, rename/changed postcondition, disabled target and in-flight revocation before effect;
- repeated contact and conflicting attempt reuse;
- cancellation/crash-window recovery without replay;
- malformed, extra, inconsistent and hung worker responses with child reaping;
- explicit failed/completed/unknown Core outcomes flowing through the registered Unity component;
- a real Windows UIA button invocation plus independent postcondition and press-count verification.

## Verification executed

```text
.\scripts\build-embodiment.ps1 -TestOnly
  Unity 6.6 PlayMode: 15 passed, 0 failed, 0 skipped

.\scripts\verify.ps1
  Ruff: passed
  strict mypy: passed across 144 source files
  generated schemas: fresh
  pytest: 261 passed, 5 explicit opt-in skips

.\scripts\verify-embodiment.ps1
  portable C#: 22 passed
  Python embodiment: 35 passed, 1 packaged-player skip

.\scripts\verify-desktop.ps1 -Native
  windows_bridge, windows_action and uia_fixture: build succeeded with 0 warnings/errors
  native-enabled desktop suite: 36 passed, 1 separate elevated/inaccessible-matrix skip

SORA_TEST_UIA=1 pytest tests/desktop/test_native_action.py -q
  1 passed
```

The ordinary suite intentionally skips the native UIA fixture, live privilege matrix, portable C#
probe and packaged player unless their environment flags are enabled. The desktop-native gate enabled
both owned UIA fixtures; its only skip was the independent elevated/inaccessible matrix already closed
under P10.1. The packaged Unity player was not rebuilt for this source-level stage.

## Remaining boundary

P11.3 provides the real target-bound PRESS primitive and its registered Unity action component. It
does not claim a complete user-facing walk/reach/pause recording, arbitrary controls, coordinate
clicking, text entry, Level 4 autonomy, or a rebuilt packaged player. P11.4 is responsible for the
deterministic media Pause fixture and the full interaction-coordinator choreography.
