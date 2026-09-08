# SORA public contracts

Version `1.0` contracts are generated from the strict Pydantic models in `src/sora/contracts`.
Committed JSON Schemas live in `contracts/schema/v1`; valid and adversarial examples live in
`contracts/examples/v1`. Regenerate schemas with:

```powershell
uv run --locked python scripts/export-contracts.py
```

`scripts/verify.ps1` checks that committed schemas exactly match the source models.

## Compatibility rules

- Every public envelope carries `schema_version`; version `1.0` readers reject missing, unknown, or
  extra fields rather than guessing.
- Additive optional fields require a reviewed minor compatibility decision. Required-field,
  semantic, enum, or type changes require a new contract version and migration/translation path.
- Provider-native session data, errors, and events are normalized at the adapter boundary. Fields
  such as Hermes tokens, Codex thread objects, or Antigravity response classes never enter Core
  contracts.
- Unsupported provider operations return the typed `unsupported` error. They are not reported as
  successful no-ops.
- Task, agent run, and provider session are separate records. A retry adds a new run; it does not
  rewrite an earlier terminal run or duplicate the user's task.
- `reasoning` means a backend is performing inference/planning without a declared external effect.
  `working` means an authorized tool/workspace operation may be underway. Neither is completion.
- Persist scheduling intent before launch. `uncertain_launch` and `lost_session` are inspectable
  states/errors; callers reconcile them rather than blindly relaunching.
- Results and patches are accepted independently. A result may remain as evidence when its patch is
  stale, denied, malformed, cancelled, or otherwise unapplied.
- Patch idempotency is keyed separately from patch ID. Entity preconditions—not global revision age
  alone—determine conflicts. Duplicate idempotency keys produce no repeated state effect.
- Event delivery is at least once. Consumers deduplicate by event ID, require contiguous per-stream
  sequence, and explicitly resnapshot/replay on a gap.
- A cancelled task may retain a late result as evidence, but its patch is not automatically applied.
- Only persisted, active, scoped grants authorize tools, paths, or desktop actions. Instructions in
  prompts, files, UI text, memories, provider results, or event payloads cannot create or widen a
  grant.

