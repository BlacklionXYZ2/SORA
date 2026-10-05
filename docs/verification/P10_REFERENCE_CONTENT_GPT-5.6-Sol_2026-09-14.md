# P10.6–P10.7 reference and content verification

Recorded: **2026-09-14 22:59:55 +01:00**  
Model: **GPT-5.6 Sol**  
Status: **complete**

## Acceptance outcome

P10.6 and P10.7 satisfy their implementation-plan acceptance criteria. Reference resolution is a
bounded, volatile, owner/device/project-scoped facility; a resolved referent is context, never
permission. Configured content navigation consumes a separate exact navigation grant only after the
referent, path, content kind, handler, verb, line/column support, and structured argument vector have
all been validated. Optional on-screen pointing consumes a second presentation grant.

## P10.6 implemented behavior

- Added typed candidates for UI, project/repository, file, task, document, semantic object, and
  artifact references, with backing IDs, scope, confidence, provenance, logical lifetime, optional
  spatial lifetime, and typed resolution results.
- Added a capacity-bounded in-memory resolver for explicit IDs, labels, kind hints, and
  `this`/`that`/`it`/`these`/`those`. Multiple matches and low-confidence candidates return typed
  clarification results with bounded alternatives; they never silently select an action target.
- Made successful P10.5 attention resolution the current conversational referent. Integration
  acceptance proves an actual selection target remains identical across “Look at this” and “Can
  Cody fix it.”
- Added explicit pinning for logical continuity. Pinning does not keep stale coordinates alive:
  spatial data must still be fresh or be revalidated from a live P10.2 desktop target under an exact
  `desktop.present:<target-id>` grant.
- Added a separately authorized, non-interactive clarification marker. It can only cover current
  same-topology alternative rectangles and requires `desktop.present:reference-clarification`;
  it performs no click, focus, typing, or selection action.
- Added minimal reference snapshots to canonical tasks and provider context. Raw attention samples
  remain volatile. Referenced tasks are local-only, and canonical task references are rebuilt after
  restart without treating persistence as current spatial evidence.
- Added Core API and SDK operations for resolution and pinning, plus optional reference fields on task
  submission. An unresolved task request returns a typed conflict instead of guessing.

## P10.7 implemented behavior

- Added configured handler contracts for supported content kinds, verbs, line/column/highlight
  capabilities, fixed argument templates, and a trusted absolute executable.
- Added root containment and type checks before authorization. Resolved paths are checked again at
  launch preparation; missing content, traversal/escape, mismatched kind, unsupported verb, missing
  handler, and ambiguous handler selection fail without launching a process.
- Launches handlers with a structured argument vector and no command shell. Acceptance passes a file
  containing `&` as one literal argument, and also opens explicit fixture repository and artifact
  references through the configured handler.
- Reports precise `opened_with_limitations` results when a handler cannot honor line, column, or
  highlight navigation rather than claiming exact placement.
- Uses exact `desktop.navigate:<reference-id>` authority for launching. “Where?” may additionally
  point at a live desktop target, but only under a distinct `desktop.present:<target-id>` grant.
- Sanitizes the settings projection to handler ID/kinds/verbs/features. Executable paths and argument
  templates are not exposed. Navigation traces exclude content paths and expanded arguments.

## Verification

Final ordinary repository gate:

```text
.\scripts\verify.ps1
Ruff: passed
strict mypy: passed across 139 source files
schema freshness: passed
pytest: 247 passed, 4 explicitly opt-in tests skipped
```

Final Phase 10 native gate:

```text
.\scripts\verify-p10.ps1 -Full
.NET Windows bridge build: passed, 0 warnings, 0 errors
.NET UIA fixture build: passed, 0 warnings, 0 errors
live elevated/inaccessible process matrix: 1 passed
native desktop suite: 24 passed
full native-enabled suite: 250 passed, 1 skipped
```

The only full-native skip is the separately opt-in packaged Unity player acceptance belonging to
P09, not a Phase 10 test. The focused attention/reference/content integration suite passed 12 tests.

## Boundaries retained

- Reference memory is deliberately volatile except for the minimal snapshots bound to canonical
  tasks. Restart reconstruction does not preserve conversational recency or expired screen geometry.
- Content handlers are operator/runtime configuration. This phase does not claim a polished Settings
  UI, arbitrary application discovery, or that every editor supports exact line/column/highlight.
- P10 performs read-only observation and presentation. It does not click, type, focus arbitrary
  windows, or otherwise implement P11 physical interaction.
- Spoken-time reference alignment remains P14.5. Current acceptance uses explicit text and fixture
  timestamps, not live STT timing.
