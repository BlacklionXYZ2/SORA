# P10.2–P10.3 Target Lifecycle and Presentation Verification

- Model: GPT-5.6 Sol
- Completed: 2026-09-10 19:18:16 +01:00 (Europe/London)
- Status: P10.2 and P10.3 complete; P10.1 remains in review; P10.4–P10.7 and overall P10 remain open
- Foundation: GPT 6 Astra's P10.1 bounded Windows observation bridge and accepted P09 coordinate/marker command channel

## Delivered boundary

P10.2 converts a selected UIA observation into a short-lived Core-owned `DesktopTarget` without treating PID, HWND, UIA runtime ID, labels, or geometry as authorization. Targets are kept only in a bounded in-memory registry, expire within five minutes, and are scoped to owner, device, and project.

Level 0 observation, Level 1 presentation, and Level 2 navigation now use distinct `CapabilityOperation` values and exact resources:

| Level | Operation | Resource |
|---|---|---|
| 0 Observe | `desktop.observe` | `desktop.observe:<process-id>` |
| 1 Present | `desktop.present` | `desktop.present:<target-id>` |
| 2 Navigate | `desktop.navigate` | `desktop.navigate:<target-id>` |

A grant for one level is not accepted for another. Every presentation/navigation revalidation consumes the supplied grant before the worker and rechecks the persisted grant, approval, actor, operation, resource, owner, device, project, expiry, revocation, exhaustion, and unchanged evidence after the worker returns.

Target identity combines the process start time, root HWND, UIA runtime ID where available, native child HWND where available, automation ID, and control type. Revalidation reruns the bounded tree observation. Expired, offscreen, closed, restarted, ambiguous, truncated-uncertain, cross-device, revoked, or stale-layout targets cannot return an active target.

P10.3 maps a freshly revalidated Level 1 target to the existing P09 presentation channel:

- `walk` → `move_to`
- `turn` → `look_at`
- `point` → `show_marker`

Commands use the freshly observed target center and topology revision. Pointing includes the verified control rectangle and target identity. A moved control updates the command geometry; a disappeared or ambiguous control queues no command. This slice performs no window focus, UIA InvokePattern, pointer movement, keyboard input, or other OS action.

## Test evidence

The added portable tests cover:

- bounded target count and explicit expiry;
- unique, missing, ambiguous and truncated selectors;
- cross-device target isolation;
- PID reuse through changed process start time;
- closed/disappeared UIA trees;
- stale display topology;
- revoked and in-flight-revoked authority;
- generic `tool.invoke` no longer satisfying desktop observation;
- presentation authority not satisfying navigation and navigation authority not satisfying presentation;
- moved-control revalidation for walk, turn, and point;
- command delivery authority invalidation;
- API acquisition, revalidation, and presentation routes.

The real Windows fixture additionally proves:

- .NET returns a parseable process start timestamp and UIA runtime ID;
- Core acquires the real `fixture-confirm` button from those identifiers;
- a second native traversal revalidates the same control;
- the queued point command retains the target ID and independently measured button rectangle;
- the bridge remains read-only and the existing hang/unavailable/password/bounds/grant tests continue to pass.

## Commands and results

### Native desktop gate

```powershell
.\scripts\verify-desktop.ps1 -Native
```

Result: both .NET projects built with zero warnings/errors; **20 tests passed in 3.61 seconds**.

### Repository gate

```powershell
.\scripts\verify.ps1
```

Result:

- Ruff passed.
- Strict mypy passed over 126 source files.
- Published contract schemas were fresh.
- Pytest: **232 passed, 3 skipped in 20.99 seconds**; skips were the explicit native UIA, .NET transport, and packaged Unity opt-ins.
- Compileall passed.

### Native-enabled full suite

```powershell
$env:SORA_TEST_CSHARP = '1'
$env:SORA_TEST_UIA = '1'
uv run --locked pytest -q
```

Result: **234 passed, 1 skipped in 23.53 seconds**. The only skip was the separately opt-in packaged Unity player already covered by Astra's P09 evidence; it was not rebuilt or rerun for this Core/bridge continuation.

## Remaining P10 work

- P10.1 still needs the live inaccessible/elevated-application matrix described by Astra; deterministic classification tests are not relabeled as live evidence.
- P10.4 was completed later on 2026-09-10; see `P10_EDITOR_HANDOFF_GPT-5.6-Sol_2026-09-10.md`. This earlier P10.2–P10.3 completion boundary remains unchanged.
- P10.5 volatile cursor/selection acquisition and geometric gesture acceptance are not implemented.
- P10.6 conversational reference reuse/clarification is not implemented.
- P10.7 configured real-content navigation is not implemented.
- Level 2 is an authorization and safe-revalidation boundary only; no focus/open/minimize action is claimed yet.

No stage, commit, tag, focus change, pointer injection, or UI semantic action was performed.
