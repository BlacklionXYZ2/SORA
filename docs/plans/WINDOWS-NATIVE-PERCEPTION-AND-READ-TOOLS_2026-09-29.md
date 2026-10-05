# SORA: Windows-native perception and small-model read tools

Prepared: **2026-09-29 08:50:52 +01:00 (Europe/London)**  
Author: **GPT-6 Astra**  
Status: **Plan only; implementation not started.**  
Scope: connect native Windows/window information and local files to everyday conversation; use vision only where structured information cannot answer the request.

This is an additive follow-on, not a replacement or renumbering of completed P10/P13 work. Historical completion evidence remains intact. `SORA_OVERVIEW.md` is unchanged. The [main roadmap](../../SORA_IMPLEMENTATION_PLAN.md) already specifies UI Automation before application integrations and on-demand vision; this plan makes that approach usable from normal chat.

## 1. Intended user experience

**2026-10-01 owner-direction update (GPT-6 Astra):** the [developed vision-alignment plan](VISION-ALIGNMENT_2026-10-01.md) now governs implementation. Retain this document's native-read, freshness and verification details, but replace its local per-operation grants with static GUI/JSON switches. SORA may choose any readable local file/path without a per-file request; references are locators, not permission tokens. Read-only-only dialogue and owner-supplied-path restrictions below are historical staging choices, not the product boundary. Desktop interaction is in scope, while user-file authoring delegates to larger agents by default. Startup has also advanced: the full launcher now wires all current helpers; reconcile it with Start-SORA rather than assuming every launcher lacks the bridge. Historical text is retained for attribution.

SORA should be able to answer these requests from her ordinary local chat interface:

- “What windows do I have open?” — list Windows-reported application/window information.
- “What am I working on?” — identify the foreground window, then inspect its accessible content if needed. Distinguish observed facts from guesses about the user's activity.
- “Read the selected text in Notepad.” — use the application's exposed selection/text, without taking a screenshot or changing focus.
- “What files are on my desktop?” — use the real Desktop folders, including redirected locations and Public Desktop entries.
- “Summarise that notes file on my desktop.” — resolve an unambiguous file reference and read the file, without requiring the owner to type its full path.
- “Read this file: C:\somewhere\notes.txt.” — preserve the existing ability to read any regular local file accessible to the owner's account, not just project/content roots.
- “What is in this image/canvas?” — use targeted, explicitly indicated vision when structured information is insufficient and capture is allowed.

“Autonomous” here means SORA can select the necessary **read-only steps within the owner's request**. It does not mean continuous screen recording, indiscriminate file-content ingestion, or independent clicking/typing. Desktop directory metadata is available by default in the local companion context; document bodies are fetched only for relevant requests.

## 2. Current implementation: source inspection on 2026-09-29

These findings come from code inspection for this plan, not a new live acceptance run.

| Area | Existing implementation | Missing integration |
|---|---|---|
| Native observation | `src/sora/desktop/bridge.py`, `clients/windows_bridge/Program.cs`, `src/sora/contracts/desktop.py`: process-scoped window enumeration and bounded UIA control tree | No cross-process discovery interface for dialogue; no general accessible text/value extraction |
| Isolation | One helper process per observation, busy guard, three-second deadline, 512 KiB response cap, cleanup | Preserve this design while adding operations; do not move UIA calls into Core's event loop |
| Authorization | `RuntimeService.observe_desktop` validates/consumes exact `desktop.observe:<pid>` grants and rechecks authorization/topology after return | Owner-local conversational read policy must resolve targets and supply authority without exposing grant fields to the model |
| Startup | `src/sora/__main__.py` accepts `--windows-bridge`; `scripts/start-manual-test.ps1` supplies `--windows-capture` only | Normal startup and release packaging must configure the observation helper |
| Files | `src/sora/runtime/local_files.py`: bounded regular-local-file reading, text/DOCX/image representations; no workspace-root restriction | No model-driven directory listing, file discovery, or reference-based reading |
| Dialogue | `src/sora/providers/dialogue.py`, `src/sora/runtime/service.py`: direct dialogue plus constrained motion keyword selection | No general bounded read-tool loop; existing explicit-path file command is narrow |
| Vision | Separate `/api/v1/dialogue/desktop` path and capture helper | Ordinary chat cannot choose a targeted fallback; structured reads must not silently become full-screen capture |
| Settings | `src/sora/runtime/app_settings.py`, `clients/desktop_app/ModelSettingsEditor.cs`: unified versioned settings and effect tiers | Perception preferences and effective capability status must use this store/UI, not another JSON file |
| Related state | Existing desktop targets, topology, attention, events, references and content systems | Reuse their identity/lifetime concepts; do not create a second action-authority or topology system |

The existing motion prototype remains separate. `{"motion":"wave"}` controls presentation only; it must never become a way to authorize a desktop/file read or OS action. See [motion keyword guide](../runbooks/SORA_MOTION_KEYWORDS.md).

## 3. Architecture and source selection

Core owns the observation services, authorization, reference map, budgets and provenance. The model proposes a small read call; it does not run native APIs, execute code, construct grants or define its own capabilities.

| Question/data | Preferred source | Important limitation |
|---|---|---|
| Open/foreground windows, geometry | Win32 window metadata plus existing topology | A title is not proof of document contents or its filesystem path |
| Controls, accessible selection/document text | Targeted UI Automation | Providers may expose incomplete, stale or no content |
| Desktop files and folder contents | Known Folder resolution plus filesystem metadata | Folder contents are not the rendered icon layout or all virtual Shell objects |
| Saved document contents | Direct bounded file reader; existing appropriate content handler where available | Saved file and unsaved editor buffer may differ |
| Rich application context | Existing editor/app integration where it gives more precise relevant data | Do not invent a generic app integration or require one for basic window discovery |
| Images, canvas, games, other pixels | Scoped capture plus local vision model | Vision is an estimate, not proof of structured state or action success |

Source choice follows the question, not an inflexible sequence: reading a known saved file goes straight to the file reader; reading an unsaved selection uses UIA/editor context. For a screen question, start with window metadata, inspect a relevant window, then consider pixels only if needed.

No screenshot or LLM inference is needed to refresh lightweight metadata. Preserve the existing killable native-worker boundary. “Supervision” means reliable startup configuration, health reporting, timeouts and child cleanup, not replacing the bridge with an unkillable long-lived UIA thread.

### Native Windows details

- Add an explicitly authorized desktop-window inventory operation. Do not weaken the existing process-scoped `DesktopObservationRequest` by making `process_id` optional for every operation.
- Enumerate top-level windows, annotate foreground/visibility/minimized state and physical rectangles, and cap results. Handle cloaked/tool/owner windows explicitly; avoid presenting hidden utility windows as ordinary applications.
- Reuse existing topology revisions and coordinate conventions. Discovery must work with the Unity avatar disabled; obtain authoritative native topology through the existing suitable host path or a bounded helper operation, not through model-generated geometry.
- Resolve user Desktop and Public Desktop with the Known Folder API, not `%USERPROFILE%\Desktop`. Microsoft documents current-user resolution and virtual-folder failure cases in [SHGetKnownFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath).
- Add bounded `TextPattern` selection/document reads and read-only `ValuePattern` extraction where supported. Never call selection setters, focus, invoke, realize/scroll, or value setters as part of inspection. UIA can expose text outside the viewport; label accessible document text separately from visible text. Use capped reads rather than unbounded document extraction. See Microsoft's [Text and TextRange patterns](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-about-text-and-textrange-patterns).
- Redact password/protected controls before copying names, values or text into a response. Do not elevate, request UIAccess, bypass protected desktops, or disguise access-denied as an empty successful result.

## 4. Metadata, identity and freshness

Introduce a small Core-owned perception service, with separate native inventory, directory listing and reference-resolution components. Proposed module names are implementation guidance, not a requirement to duplicate existing modules: `src/sora/perception/{service,references,files}.py` and `src/sora/contracts/perception.py`.

Each result carries a snapshot ID, source, capture time, status, truncation indicator and optional continuation cursor. Window observations also carry topology revision and verified process identity. Use UTC internally; display local time in UI/evidence.

Model-facing references are short opaque IDs such as `w1`, `d1`, `f3`. Internally bind them to owner/device/session, snapshot, expiry and actual identity:

- Window: HWND, PID, process start identity and topology revision. Revalidate before/after inspection; window closure or handle/PID reuse invalidates the reference.
- File: canonical local path and recorded metadata; re-resolve before reading. If the item changed/replaced since listing, refresh/report the change instead of presenting old metadata as current proof.
- Directory: canonical path, snapshot and continuation state. Cursors are Core-issued, bounded and session-scoped; the model cannot use them to widen access.

Start with on-demand refresh and short-lived caches. A cheap metadata refresh may run at local session start/foreground changes, with debouncing and a bounded fallback timer only if needed. Reuse existing event infrastructure where practical. No background UIA document scraping, recursive drive crawl or periodic inference.

Proposed initial bounds, subject to measurement during implementation:

| Resource | Initial bound |
|---|---|
| Cached metadata age | Windows 2 seconds; Desktop listing 10 seconds; explicit “now/refresh” bypasses cache |
| Window inventory | 64 entries, explicit partial-result marker |
| Directory listing | 100 entries/page; no recursive traversal by default |
| UIA | Existing default 128 nodes/depth 6 and hard 256 nodes/depth 12; 3-second helper timeout, 512 KiB output maximum |
| Extracted UIA text | 8,000 characters per inspection, bounded across nodes rather than per node |
| Read loop | At most 4 tool executions per turn, no parallel model-selected calls, one identical-call retry maximum |
| Per-turn retrieval deadline | 15 seconds for read execution, additionally bounded by the existing dialogue timeout including model calls |
| Model observation budget | At most 8,000 characters and never more than the configured total prompt budget; reserve space for owner request, instructions and answer |

Reference expiry is short and explicit (initially 60 seconds), and freshness checks still apply within that time. Old conversation IDs cannot silently resolve to newly assigned objects. Keep a small bounded map and invalidate it on restart, logout, authorization changes or relevant topology changes.

Directory handling must preserve duplicate names across user/Public Desktop with source labels. Treat shortcuts as entries, not instructions to launch or automatically follow. Do not recursively follow junctions/symlinks. Reject resolved network/device paths, including mapped-network destinations; do not assume a drive letter is local. Cloud placeholders may be listed but must not be silently hydrated as a background inventory side effect. Return `not_local`/`unavailable` for unavailable content rather than downloading it implicitly.

## 5. Small-model read schema and orchestration

Use the same configured low-cost local dialogue model; do not add a large-model dependency. Reuse the constrained-output adapter pattern from motion selection and validate every result in Core. Implement a separate read-capable provider protocol so existing deterministic/other providers can truthfully report unsupported capability.

The proposed wire shape is deliberately small: `tool`, `target`, `cursor`. All three keys are required; unused values are `null`; additional properties are forbidden. The semantic validator enforces valid combinations. Schema-constrained output is not itself authorization.

```json
{"tool":"list_windows","target":null,"cursor":null}
{"tool":"inspect_window","target":"w1","cursor":null}
{"tool":"list_files","target":"desktop","cursor":null}
{"tool":"read_file","target":"f3","cursor":null}
{"tool":"done","target":null,"cursor":null}
```

These are separate example calls, not a batch. Initial enum: `done`, `list_windows`, `inspect_window`, `list_files`, `read_file`. `inspect_window` returns a compact tree plus relevant accessible selection/text; do not require the 2B model to supply UIA selectors or native handles. `list_files` accepts `desktop` or an issued directory reference. Reading an owner-supplied absolute path first creates a Core reference using the existing reader validation; arbitrary paths are not executable model arguments.

The owner may ask for a path outside Desktop. Resolve that literal path or an already established directory reference; Desktop is the default discovery location, **not an access sandbox**. Broad “find it somewhere on my computer” recursive search is out of v1; ask for a location or offer an explicit bounded listing. Do not pretend every local file has been indexed.

Keep existing `MotionChoice` unchanged. At turn entry, determine allowed task families from the owner request and trusted conversation state, before adding external observations. Do not run the motion classifier on file/window results. Inspection-only turns cannot dispatch motion, board commands, shell calls, typing, navigation or writes. Mixed read/action requests are deferred or clarified in v1 rather than escalating a read loop into an action loop.

### Turn lifecycle

1. Authenticate local-owner origin; snapshot the provider session/settings revision and effective read permissions. Do not let a caller-supplied boolean impersonate the owner.
2. Compile a compact context header: capability availability, actual Desktop directory references, foreground-window metadata and a small relevant Desktop inventory. Keep the bulk inventory in Core, not the prompt. Omit private context entirely for nonlocal/remote model endpoints and remote clients.
3. Ask for a read-tool decision using the owner request and permitted read vocabulary. Ordinary conversation chooses `done` without retrieving document bodies. Follow-up referents use validated conversation references, not invented paths.
4. Validate arguments, relevance/scope, live reference and budgets; authorize the read in Core. Perform the bounded operation and recheck authorization before delivery.
5. Return a typed tool result as **untrusted external data**, with source and status. Re-enter the read selector only while within the owner-authorized scope and budgets.
6. On `done` or exhaustion, generate the answer using available evidence. On timeout/invalid output, stop tool execution and offer a truthful partial answer/error; do not repair free text into executable calls or repeatedly retry the model.
7. Discard transient bodies/capture data at turn end. Keep only policy-appropriate metadata/provenance and ordinary conversation records.

Tool result status vocabulary should distinguish `ok`, `partial`, `unsupported`, `not_configured`, `access_denied`, `not_found`, `ambiguous`, `stale`, `timeout`, `busy`, `invalid_request` and `budget_exceeded`. Map existing bridge statuses without losing their diagnostic detail. An empty list is only successful when enumeration genuinely returned no entries.

Prompt injection cannot be addressed by a warning string alone. External content must not expand the allowed tool families or reference scope: in v1, return file/text bodies to the final-answer step, not to a planner allowed to discover unrelated files. Permit multi-step selection from bounded listings, but restrict selectable references to the owner's requested location/window. A file saying “read another private file” cannot authorize that read. Keep a blocked-instruction fixture in regression tests.

## 6. Authorization, privacy and storage

- Preserve the owner's explicit preference: any readable **local** regular file may be requested, without per-file approval popups or a project-root allowlist. Normal OS permissions and resource limits still apply.
- Persist owner-controlled read preferences; derive short-lived, exact operation grants in Core where the desktop API requires them. The persisted owner policy is the authority source, not the LLM's claimed intent. Add a distinct exact inventory resource rather than a wildcard process grant. Test revocation before and after helper execution.
- Defaults proposed for this local-owner installation: Desktop metadata context on; native window inspection on request; local file reads on request; automatic vision fallback off. Expose these controls and their scope visibly in Settings.
- Remote paired clients, guests and specialist agents do not inherit local-owner window/file access. Check every API/stream/voice entry point; new tools and private metadata must be structurally absent where disallowed, even if a request supplies forged IDs.
- Private window titles, filenames, UI text and file bodies go only to a validated loopback dialogue endpoint under the existing local-data boundary. Recheck effective endpoint on model reload; never carry private cached context into a newly selected remote provider. Loopback validation does not certify what a third-party local proxy does downstream; state that limitation in the guide.
- Password UI content remains redacted. Do not automatically open credential files just because they appear in a directory listing. Explicit owner file requests still use the established local-file policy.
- Raw UIA trees, directory inventories, document bodies and screenshots are transient, not automatic long-term memory or generic event payloads. Trace status/source/timing/counts instead of raw content/full paths. Explain that normal user messages and assistant answers can still include filenames or requested excerpts and follow existing chat retention.
- Logs remain human-readable. JSON contracts are internal transport; owner-facing diagnostics explain source, age, result and limitation plainly.

## 7. GUI, startup and vision fallback

### Everyday startup and Settings

- Build/configure the trusted observation helper alongside capture in `scripts/start-manual-test.ps1` and verify the `Start-SORA.ps1` path. Audit release builder/install paths so the packaged app receives the same capability, not only development startup.
- Helper absence disables perception with an actionable status, without preventing ordinary conversation or avatar startup. Track only owned child processes; shutdown must not kill another SORA instance or an unrelated model server.
- Extend unified `AppSettings` with a perception section, using explicit migration/version compatibility, schema export, atomic saves and existing conflict recovery. Do not create a parallel perception configuration file or overwrite model settings during migration.
- Add GUI switches for Desktop context, window inspection, local-file reads and automatic visual fallback. Toggle revocation/cache clearing is live; helper installation/path changes may require restart and must be labelled accordingly. Resource budgets can remain advanced bounded settings.
- Show effective status: “Windows information ready”, “Helper unavailable”, “Local model required”, “Reading window”, or “Reading file”. Include cancellation and compact expandable provenance; do not require navigating raw grant IDs.
- Preserve attachment and explicit-path flows. Update “Look at screen” help to distinguish pixel capture from native window information. Do not silently change an explicitly requested screenshot into metadata-only inspection.

### Visual fallback

After structured reads are working, add `capture_window` as a separately gated enum member using an existing valid window reference. Do not expose arbitrary rectangle coordinates to the model in v1.

- Available only for explicit visual requests or when the owner enables automatic fallback within a relevant request, and only with capture authority plus a working local vision model/projector.
- One targeted capture per turn initially. Revalidate window bounds/topology immediately before capture; do not focus/raise a window just to see it.
- A screen-region crop is not necessarily an unobscured window image. Detect/report minimized, offscreen or occluded limitations; do not claim another covering window's pixels are the target's contents.
- Retain the existing explicit whole-display “Look at screen” path. No silent expansion from a failed window crop to the full desktop. Secure/protected content remains unavailable.
- Reuse frame TTL/deletion and cancellation cleanup. Display that vision was used and why; mark visual interpretations separately from Windows-reported facts.

## 8. Implementation stages and completion gates

Use `NP1`–`NP7` as follow-on identifiers; do not claim new numbered roadmap phases without an agreed mapping. Implement and verify in dependency order. All completion fields below are intentionally empty.

| Stage | Deliverables | Acceptance gate | Status / completed at |
|---|---|---|---|
| NP1: contracts and policy | Typed inventory/read results, reference lifecycle, exact inventory authority, read policy, settings migration and test fixtures | Invalid payloads/foreign IDs/stale refs rejected; existing grant behavior unchanged; old settings import losslessly | Planned / — |
| NP2: native discovery and startup | Bounded desktop-window inventory, foreground identity, Known Folder paths, helper health; normal and packaged launch wiring | Real fixture windows enumerated without screenshots/inference; avatar-off startup works; missing/hung helper degrades cleanly | Planned / — |
| NP3: useful structured content | Bounded UIA text/selection/value reads, directory pages, reference-based reuse of local-file reader | Saved file vs unsaved text distinguished; password redaction, duplicate names, redirected Desktop and stale targets covered | Planned / — |
| NP4: small-model read dialogue | Constrained read protocol, compact context, bounded loop, trusted scope and answer provenance | Normal chat completes window and Desktop-file prompts on actual low-cost model; no screenshot needed; ordinary/motion/attachment regressions pass | Planned / — |
| NP5: Settings and user-facing integration | Full-app settings/status/cancel/source UX, widget parity, cache revocation and restart/provider-reload behavior | Owner can enable/disable/inspect capability without editing JSON; disable takes effect immediately; no private remote context | Planned / — |
| NP6: targeted visual fallback | Gated capture choice and evidence-labelled response, retaining explicit screenshot button | Structured-readable test uses zero captures; inaccessible canvas falls back only when allowed; projector/occlusion/denial failures truthful | Planned / — |
| NP7: acceptance and handoff | Deterministic/native/live-model/GUI checks, runbook, evidence summary, manual-owner checklist | All mandatory tests have actual results; remaining manual/unsupported cases explicitly listed; no blanket “full desktop access works” claim | Planned / — |

NP1 settings schema precedes NP5 UI; NP2 supplies the real paths and identities consumed by NP3; NP4 is the first useful chat milestone. Stop after each stage to record evidence, exact completion date/time with timezone and a separate `changelog/<timestamp>_NPx_<model-name>.md`. Use **GPT-6 Astra** for this implementer's attribution. Distinguish implemented, in review and verified complete; never fill completion timestamps for planned work.

### Expected touchpoints

- Contracts/exports: `src/sora/contracts/desktop.py`, new perception contracts as needed, `src/sora/contracts/registry.py`, generated `contracts/schema/v1/*`.
- Native: `clients/windows_bridge/Program.cs` and its tests/fixture; `src/sora/desktop/bridge.py`; reuse `desktop/targets.py`, events and topology infrastructure.
- Core: new bounded perception service; `src/sora/runtime/service.py`, `local_files.py`, `app_settings.py`; `src/sora/providers/dialogue.py`; API request context in `src/sora/api/routes.py`.
- Clients/startup: `clients/desktop_app/ModelSettingsEditor.cs`, `FullAppForm.cs`, shared widget/client models as needed; `src/sora/__main__.py`, manual launcher and release scripts.
- Tests: existing desktop/provider/settings suites, new perception unit tests, C# fixtures, opt-in live-model acceptance and user-side GUI checks.

Keep native, file, reference and dialogue orchestration responsibilities separate; avoid putting the entire feature into more branches in `RuntimeService`. Reuse existing references where compatible, but do not confuse an observation reference with an authorized action target.

## 9. Verification matrix

| Layer | Required checks |
|---|---|
| Deterministic contracts/policy | Extra fields, unknown tools, forged target/cursor, expiry, owner/device mismatch, remote rejection, grant exhaustion/revocation, endpoint changes, budgets and cancellation |
| Native fixture | Two windows in different processes, foreground changes, minimized/closed/reused identities, normal controls, selection, unsaved text, password field, unsupported provider, hung helper and cleanup |
| Files | User/Public Desktop, redirected path, duplicates, spaces/Unicode, nonexistent/access-denied file, modifications since listing, large/truncated file, binary unsupported semantics, shortcuts/junctions, network/device paths, cloud placeholders |
| Injection/behavior | File/window text asking for unrelated secrets/actions; quoted/negated requests; capability questions; ordinary greeting; ambiguous “that file”; scope cannot widen; no motion/action dispatch from observations |
| Live low-cost model | Multi-step list→read and list→inspect, correct tool arguments, honest unavailable answers, continuation/budget exit, source-grounded final answers; record model filename, quantization, server version/config and timings |
| GUI/restart | Normal single-script startup, full app and widget chat, attach-file regression, switches/status, cancellation, unavailable helper, settings save/restart/reload, no leftover owned helpers |
| Vision | No capture on structured paths, explicit capture still works, targeted fallback with/without permission/projector, occlusion/minimized behavior, frame expiry and deletion |
| Regression | Motion keyword dispatch remains separate and grant-backed; existing desktop actions/references, settings rollback, remote surfaces and regular dialogue still behave correctly |

Run targeted tests during each stage, then the repository gate (`scripts/verify.ps1`). When schemas change, run `uv run --locked python scripts/export-contracts.py` first. Run relevant native checks (`scripts/verify-desktop.ps1 -Native` and current applicable desktop/C# suites after confirming their interfaces). GUI/native tests must use isolated profiles and fixtures and preserve existing user processes/data. Do not claim Unity rendering tests passed when only Core/API state was checked.

Measure native enumeration, UIA inspection, file listing/read and model routing separately. Record cold/warm timings and prompt payload size; compare native-text answers with the screenshot path on the same benign fixture. Performance budgets above are initial design limits, not measured results. Never call vision “slower by X” without recording an actual comparison.

Required owner-facing acceptance prompts:

1. “What windows do I have open?” — accurate bounded list, no screenshot.
2. “Read the selected text in the test editor.” — correct selection, no focus/input side effect.
3. “What files are on my desktop?” — real folder metadata, explicit partial listing if capped.
4. “Summarise the test notes file on my desktop.” — resolves and reads the right file; asks if duplicate names are ambiguous.
5. “Read file C:\<fixture-outside-project>\notes.txt.” — succeeds without a project-root restriction or per-file popup.
6. “What is in this canvas?” — honest structured limitation, then permitted targeted vision or a clear option to enable it.
7. Disable perception and repeat — no new observations, cached context cleared, clear explanation.
8. Repeat from a remote paired client — no implicit access to local window/file inventory.

Live tests should use benign fixture content. Elevated/protected apps, redirected/cloud Desktop, mixed-DPI/monitor changes and real application UIA coverage require explicit actual results or an owner/manual-unverified entry, not mock-based blanket acceptance.

## 10. Rollout, limits and deferred work

Ship the structured path first behind the owner-local settings. Keep legacy explicit attachments/file reads and capture usable while integrating. A missing/unsupported read provider must leave normal chat usable and explain unavailable tools, not crash every turn. Disabling the feature cancels reads, invalidates references and removes private prompt context; rollback preserves the settings backup and ordinary dialogue.

This plan does **not** implement broad filesystem indexing, recursive search, semantic extraction of every file format, network shares, automatic cloud downloads, continuous visual monitoring, arbitrary app adapters, OS action planning, parameterised avatar motion, or learned animation. Binary hex output is not a successful document summary.

The first release targets local text chat in the full app/widget. Voice has a separate orchestration path: audit it for isolation, but do not claim voice can call the new tools until a later explicit integration with the same policy, cancellation and spoken-reference tests. Remote-owner parity is likewise not implicit.

Final handoff must include a readable runbook, a verification report separating live proof from mocks/manual gaps, and model-attributed stage changelogs. At the end, SORA should be able to inspect appropriate Windows information and requested local files from ordinary conversation without making screenshots the default source of truth.
