# GUI-2 shared categorized Settings — verification

Model name: **GPT-6.1 Sol**. Implementation checkpoint: **2026-10-04 07:21:29 +01:00**, Europe/London; final source/test/build/preservation checkpoint **07:33:44 +01:00**. Status: **implemented slice / GUI-2a/b/c/d in progress**, not stage completion.

## Delivered source and authority

The shared profile host replaces its read-only Settings probe with `SettingsForm` hosting the complete existing schema-driven `ModelSettingsEditor`. The standalone GUI-0 prototype retains its named probe. The editor also remains the compatibility Desktop editor. No extra timer, synchronizer, HTTP/inference connection, audio worker, canonical settings store or alternate authorization layer is introduced.

All84 editable canonical AppSettings v9 leaves have explicit category/disclosure metadata; a Python coverage test matches the actual recursively flattened model, unique keys and effect tiers. [Field map](../gui/GUI2_SETTINGS_FIELD_MAP_GPT-6.1-Sol_2026-10-04.md) records every field. Ten categories include honest unavailable Memory/Automation descriptions and a link to the existing separate UI-only Appearance store. Older running v9 Cores have matching client category/disclosure fallback; selected examples and unknown-field retention are component-tested. There is no settings-version bump or default/policy change. Supplied Settings reference image inspected with the local image viewer; no new native screenshot is claimed.

Models presents actual projected saved/effective GGUF, dialogue backend, external model, model state, context/cache/flash settings and runtime-support text. These are Core configuration/status reports, not independently measured GPU load or provider entitlement. VRAM/capabilities absent from Core are explicitly unavailable. No guessed metrics, fabricated loaded-model capability card, editable arbitrary launch flags or unsupported controls. Read-only sanitized actual launch arguments remain to be implemented.

Static access/perception controls retain the owner's direction: no renewed per-file/window permissions. Agent preferred model/effort/purposes/shortlist/project/workspace/base-ref controls and task deadline are retained, with shared Agents/Paths/Voice/Integrations links. Descriptive metadata is not model access. Disabling local agents/voice has its existing Core effect; no policy is inferred from the avatar.

## Save, conflict and asynchronous behavior

The Settings adapter has a fixed route vocabulary. Save/disk refresh/model reload serialize in the shared Core effect slot. Save re-reads canonical version/revision/editable fields before admission; the existing instance-bound transport and explicit profile identity checks fence effects and acknowledgements. Wrong/stale revisions, external disk edits, unsupported fields/routes/bodies, unavailable Core and non-reloadable state are rejected before POST. Acknowledgement shape/revision and Core identity are checked; no automatic effect retry. Revision/read-generation fences prevent a late successful or failed poll from replacing/invalidation of a confirmed Save.

`SettingsDraftState` retains the draft baseline across fresh/conflicting projections, protects Save from later edits, treats missing/wrong/late acknowledgements as unknown, and prohibits discard during a pending Save. Editor controls lock during awaits; lifetime cancellation and disposed checks prevent late projector/save updates. Reload is disabled with dirty/conflicting/unknown drafts and binds confirmation to its captured revision/epoch. Model/projector browsing remains an unsaved draft operation; multiple adjacent projectors require explicit choice, compatibility still depends on actual load.

**Reconcile draft** is read-only until its separate later Save. Review displays previous/current/local edited values. Acceptance adopts current saved values for untouched controls, keeps only the actual local edits and changes the draft baseline explicitly. Pure tests prove untouched concurrent edits are not reverted, originals/current maps remain unchanged and changed field identity is rejected. A changed epoch/revision during review rejects reconciliation without submission. Native review/mouse/keyboard/purpose-control behavior remains unverified. **Discard draft** is the explicit alternative; uncertain outcomes do not automatically resend an effect.

Closing hosted Settings hides it without discarding. Pending effects/modal edits block Quit; dirty drafts require a foreground consequence decision. IPC Quit refuses dirty Settings; accepted shutdown freezes further Settings edits, and failed/deferred shutdown re-enables the editor. Actual hide/Quit races require native proof. An initial offline Core yields diagnostics, not fabricated saved defaults; retained saved state/draft remains inspectable offline with effects disabled.

Disk refresh explicitly warns it applies live changes and may stop voice/revoke agent runs; it is not an innocuous GET. Existing Core validation-before-reload-stop, byte-preserving invalid-file backup, recovery copy and last-good rollback remain unchanged and covered by existing Python tests. No real owner model reload/failure or file replacement was invoked here.

Audio device combos preserve drafts and offer only current unique direction-compatible actual keys. Blank means Windows default; ambiguous/stale inventory is not silently selected or used to Start audio. The host consumes its one existing voice-status inventory. No physical device enumeration/input/output acceptance was performed.

## Fresh verification

| Command/check | Actual result |
|---|---|
| `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet` | **273 passed**, zero failed/skipped, final run warning-free |
| `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003; ./scripts/verify.ps1` | **711 Python passed /25 opt-in skipped in87.53s**, **8 PWA passed**; mypy267/lint/generated schema/compile pass; exec13087 final exit0 |
| Final Shell/Desktop/Widget builds | all three zero warnings/errors |
| `./scripts/verify-shell-launchers.ps1` | actual-full-launcher effect-free defaults/explicit/retained-panel/unsupported-effort checks pass |
| Targeted Python AppSettings | **12 passed /1 real-model opt-in skipped** before full verify |
| Preservation | original nine reference/baseline artifacts and the three historical completed checkboxes checked separately; no stage newly checked complete |

New component coverage includes draft revision/epoch conflict, late-save edit retention, exact acknowledgement revision/version/epoch, unknown no-replay, explicit reconciliation, untouched-current-value retention, category fallback, host unavailable/disposed/read-only states, closed routes/fields, fresh preflight, save serialization, replaced Core before/after POST, late successful/failed settings polls and distinct explicit refresh/reload effects. This is not a user-side GUI acceptance result.

## Open gate / next work

Actual Settings category/disclosure/row sizing and DPI/text/high-contrast/keyboard/accessibility rendering; purpose/path/reconciliation dialog input/cancel/save/restart; microphone/speaker picker unavailable/ambiguous/physical behavior; real model reload/error/last-good recovery; static disables across restart; provider entitlement; sanitized read-only actual launch details and final reference styling. Earlier GUI-0b/GUI-1 native/lifecycle/voice/retained-workflow gates remain open. GUI-3 Memory/semantic, GUI-4 scheduler, GUI-5 graph/design and GUI-6 ordinary launch/release remain required.

No equivalent retry of the earlier policy-denied fixture/native-launch workflow was made. Current owner Core **PID52000**, original start **2026-09-29T21:49:32.7934609+01:00**, still runs from the existing `.venv`; this slice did not stop/restart it, edit its settings, load a model, enumerate physical audio or change the ordinary Desktop default. Verification used the isolated frontend environment. No commit/reset or material deletion.
