# Agents and model selection

This is specialist task selection, separate from SORA's local conversational model.

In the full app, open **Activity → Agents and models…** to inspect the catalogue, or use
**Chat → Delegate as task** to select an agent for your draft. In the compact widget, use
**••• → Agents and models…**, or **Delegate**.

1. Use **Refresh models** when you need the current installed-provider listings. Opening the
   window only reads the current Core's cache. Refresh sends no task prompt/inference. Hermes
   exposes its catalogue on a new empty ACP session; MCP startup is disabled for that probe.
2. Select an agent. Model labels show both readable names and exact backend IDs.
3. Select a model, or deliberately keep **Saved preference / configured default**. Supported effort choices appear
   only where mapped. Antigravity embedded tiers have no second effort switch. Hermes currently
   has no per-run effort switch. Codex recommended effort is selected when metadata supplies it.
4. For project work, enter/browse the actual **Project** directory and select **Mode**. Blank
   project uses that agent's saved project preference. Missing destination for a write task returns
   **Which project?**, not a tool-permission request. `direct` edits in place; `isolated` explicitly
   creates a managed Git worktree; `read-only` cannot author files. Current enforced project work
   uses Codex; Hermes/Antigravity project-boundary support is not implemented and returns a typed
   unsupported result. Do not assume a catalogue listing proves filesystem containment.
5. Review the task and click **Start specialist task**. Final confirmation displays the selection.
   Cancel leaves the draft untouched. Browsing/refreshing alone never starts specialist work.

The full app's Activity table retains the **requested** model and effort. Listed means the
provider advertised that entry; it does not prove your account can execute it. A failure is not
replaced with a different model or missing agent's default. Provider defaults and SORA's dialogue
model remain unchanged. Discovery errors are visible and contain no raw credential/config dump.

The desired owner roster is shown separately from discovered access. In the current installed
Hermes catalogue, GPT-6 Luna and GPT-5.6 Luna/Terra use openai-codex: identifiers; DeepSeek Flash
uses deepseek:deepseek-flash. That alias is not proof of a particular DeepSeek version.

Open **Settings → Go to section → Agents · Codex/Hermes/Antigravity** to edit each agent's
purpose, enabled switch, preferred exact model ID, supported preferred effort and the preferred
model's purpose. **Refresh agent models** fills the editable model dropdowns without inference.
Blank model and `configured` effort preserve the harness default. Preferences and purposes live
in the same canonical `sora-settings.json` as other owner settings, not provider config files.
Preferred model/effort still selects the default. **Model shortlist and purposes → Edit…** now
adds multiple exact model IDs and descriptions per agent (up to 64). Choose a discovered ID or
type a configured one, enter its purpose and click **Add / update model**, then **Use draft** and
**Save settings**. Cancel preserves saved values. Removing a row removes only its descriptive
shortlist entry, not model files, the preferred model, or access to other provider-listed models.
The default-model purpose remains a fallback; an explicit shortlist row overrides it.

The shared **Agents and models → Edit model purposes…** editor is also available through the
compact widget's catalogue. Its **Save purposes** button saves only that agent's rows, with a
revision check; failed saves keep the dialog/draft open. It does not launch inference.
Refresh metadata explicitly when needed; unlisted configured IDs remain labelled
`configured_not_checked`. Core/model/provider rejection still does not substitute another ID.
Each agent section also provides **Project root**, **Workspace mode** and **Base ref**. Direct work
is the default; Base ref applies to opt-in isolated Git work. These are canonical app preferences,
not edits to the installed agents' own configuration files.

**Settings → Runtime → Specialist task time limit** sets the deadline for new runs (default 300
seconds; permitted 5–3600). It does not extend an already running task. Partial file changes can
exist after timeout: inspect the result and path evidence rather than assuming success or rollback.

Preferences take effect for new owner-local tasks and tasks started from the board. The selected
preference is persisted with the task; later preference edits do not change queued work or retries.
An explicit per-task model does not inherit an effort intended for another preferred model.
Disabling an agent rejects new local submissions/retries/steering; the shared delegation epoch
conservatively revokes **all existing owner-local delegated runs**, including queued work. Turning
it back on does not revive those old runs. Cancellation requests are not proof an opaque native
process has stopped. Remote/legacy authorization is not upgraded to owner-local static policy.

Settings v2–v8 migrate to v9 with a preserved original backup. Invalid/incomplete v9 access
preferences fail validation and use the existing recovery/fail-closed path. Model names are not
credentials or execution entitlement: select an advertised exact ID; rejection never substitutes
another model. Purpose text is metadata, not permission or a tool instruction.

In the full app, **Activity → Project paths and writers…** shows reserved roots and recent evidence.
The compact widget has the same view in its menu. Equal/nested/canonical-alias roots cannot acquire
overlapping declared writer reservations. Reservations have no time-based unlock: uncertain writers
remain held. **Recheck stopped writers** performs conservative Core/kernel reconciliation; it is not
a force-unlock button. The owned Codex process tree is attached before receiving its launch handshake
and stopped before normal release. Opaque agent reads are not a complete filesystem audit.

Source labels matter: `declared_root` is the selected scope, `provider_reported` is the agent's account,
`filesystem_diff` is bounded size/mtime evidence, and `core_observed` records Core lifecycle outcomes.
These do not prove the author of every change or every file read. Incomplete snapshots are labelled.
Paths/result views and newly stored project/base-ref fields are owner-local; paired task/replay
projections omit the new path fields. This is not general redaction of paths inside user-authored text.

Use **Activity → View selected result…** (or double-click the row) to read the stored result, errors,
warnings, reported file/command lists and reported changelog path without decoding JSON. A missing
agent changelog is visibly incomplete evidence, not verified completion. Changelog files are still
the agent's own account; SORA does not invent a replacement log after failure.

Full successful real-model GUI edit/changelog acceptance after the timeout repair, compact Paths
acceptance, adversarial crash/restart/alias matrix, root amendments/renewals, every adapter's boundary,
actual multi-model shortlist GUI/real-model selection acceptance and independently verified
live-model/last-success evidence remain active work. The shortlist and initial compact delegation
schema are implemented, not proof of those acceptance gates.

For developers, scripts/verify-agent-catalogue.py performs real metadata discovery and offers a
clearly labelled no-inference fixture in a dedicated repository .local directory. --serve enables
a loopback QA Core. Never choose a real agent there if you intend a no-inference GUI transport test.

## SORA's companion delegation vocabulary (implemented progress)

Owner-local conversation with a compatible local chooser can now discover agents and request one
delegation through the same Core queue used by the manual task dialog. `list_agents` returns
cached enabled purposes/models in pages; listing is not entitlement or successful inference.
`list_agents` accepts a literal model-name/ID/purpose filter and bound pagination cursor, so a
large catalogue need not be dumped into the small model's prompt. Shortlist descriptions are
descriptive/untrusted data and take precedence over provider text; other listed models remain.
`delegate` uses known project/model references or saved defaults, not arbitrary model IDs/paths.
Unknown choices fail; there is no silent replacement. Missing write destination asks Which project.

The queued chat receipt identifies task, agent, model, project and mode. It is not completion.
**Activity → View selected result…** displays the original owner's request, separately labelled
SORA suggested brief, and stored result/evidence. The brief is not forwarded as authority or agent
context in this slice. Prior desktop/chat history is not automatically forwarded for these tasks.
No general direct file writer or typing-to-file workaround has been added.

The same implemented call vocabulary includes existing native/file reads, keyword avatar poses
and pointer-only movement. Disabled operations are absent from constrained choices. One terminal
effect ends selection; unified finish does not consult a second motion selector. Dispatch does
not prove animation completion or arrival. Look/point/press/type and the full unified verifier/
result lifecycle still need their remaining planned integration.

Real small-model and full/compact/PWA/voice delegation acceptance remain open. The 2026-10-03
isolated GUI attempt captured Offline test mode but could not activate the window after recovery.
`scripts/verify-companion-calls.py` provides an explicitly offline/no-inference QA fixture in a
fresh dedicated .local state, with STOP-sentinel cleanup; it is not a model-performance test.
The editable multi-model-purpose list is now implemented. Its full/compact GUI rendering/save/
restart and actual small-model purpose-based choice still require user-side/live verification;
the 2026-10-03 attempt failed Windows activation before entering Settings.
