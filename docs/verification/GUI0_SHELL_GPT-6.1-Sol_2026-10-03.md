# GUI-0 shell feasibility — fresh evidence and limits

Contributor: **GPT-6.1 Sol**. Date: 3 October 2026. Status: GUI-0a baseline scope complete; GUI-0b prototype implemented / **in review**, not production GUI acceptance. GUI-0c/d specification scopes complete at 19:24:55 +01:00. [Roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md), [baseline/parity inventory](../gui/GUI0_BASELINE_GPT-6.1-Sol_2026-10-03.md), [ownership/interface specification](../gui/GUI0_HOST_AND_INTERFACES_GPT-6.1-Sol_2026-10-03.md).

## Implemented scope

New opt-in `.NET 10` WinForms project `clients/desktop_shell` uses the existing `WidgetApiClient` / `WidgetSync`, a shared async presenter, one connected resizable Chat prototype, independent read-only Settings/recovery probe and native bounded graph fixture with equivalent node list. Explicit loopback Core/token arguments are required. No new inference transport, canonical settings database, global desktop monitoring or renderer dispatcher was introduced. Production host/tray/singleton, launch migration and four-panel styling are not yet implemented.

Presenter behaviour includes non-overlapping refresh, separate connection/model/settings states, labelled stale cache, retained in-memory drafts, immutable submitted text, double-send prevention, exact Send/Stop nonce and typed cancellation. Stop reports Core's actual acknowledgement and does not claim to undo dispatched effects. Graph layout caps at 75 nodes, filters unknown/self/unevidenced edges and reports truncation without an invented total.

## Actual Windows GUI checks

Used the Computer Use skill and native Windows UI/screenshot inspection. Test Cores used deterministic fixtures and isolated profiles; **none of these replies was real LLM inference**. The owner Core PID 52000 was not controlled. Screenshots were inspected in tool output; this report does not claim stored screenshot assets or a recorded video.

| Check | Observed result | Evidence boundary |
|---|---|---|
| Connected Chat + Settings | Authenticated Core connected, Settings probe opened and exposed the actual 84-field projection | Fixture Core; read-only settings, no Save/Reload or security-toggle changes |
| Typed user-side conversation | Entered `Hello SORA. This is the GUI-0 conversation test.`, clicked Send, saw owner/assistant transcript | Canonical messages also verified through authenticated API; not an ordinary real-model turn |
| Canonical conversation IDs | Owner `message-c5b5ecf4-f337-457d-a873-74e2352bb684`; assistant `message-307f643b-61a7-4acc-b842-8f365470bd1f` | `.local/gui0-core-20261003`, port 18795; fixed offline QA reply explicitly disclaimed inference/effects |
| Graph/list selection | Clicked fixture node/list N5; Down selected N6, rendered highlight followed list selection | 12 labelled synthetic nodes; not SORA memory data, relationships or semantic model calling |
| Disconnect with draft | `Keep this unsent draft while Core is offline.` remained after graceful QA Core shutdown; Send disabled | Last-known projection explicitly stale; actual GUI flow used an intermediate prototype build |
| Offline Settings | Opened Settings after disconnect; cached projection marked stale | No offline save or repair executor exists in prototype |
| Initial Core connection failure | Fresh prototype opened without Core; recovery/Settings reachable and Send disabled | No fabricated current values; shell not dependent on model or avatar |
| Compact layout | Native 150% environment exposed physical/logical pixel sizing bug; fixed and rechecked readable compact layout | Actual compact prototype render, not mixed-monitor/100%/200% acceptance |
| Unavailable model / absent avatar | Final-source prototype connected to port 18796 with intentionally simulated model-down state, Send disabled; Settings still opened with 84 rows | `verify-gui-shell.py --model-unavailable`; no GGUF/server/player started, therefore not a real model-load failure test |
| Final-source DPI / text | Prototype reported **144 DPI (150%)**; disabled controls and setting names readable | Native render at existing OS scale; no OS settings changed |
| Normal QA cleanup | Settings/main forms closed via standard Alt+F4; each QA Core exited 0 on STOP sentinel; no GUI/18795/18796 listener remained | Owner Core PID 52000 still alive; production hide/Quit ownership remains future work |

Native element-coordinate activation failed once for a tab and once for a caption close control. Fresh state plus screenshot-derived tab click / standard Alt+F4 completed those interactions; they were not treated as product failure or a persistent blocker. A build attempted while an older prototype process held its executable failed with copy-lock retries; the UI was closed normally and the final build passed. No process-name kill was used.

## Changes driven by rendered inspection

Compact dimensions now convert logical pixels using actual `DeviceDpi` and clamp to the working area. Offline headers use short readable states, while diagnostics remain accessible in Settings. The Settings key column was widened with full-value tooltips. Native button semantics/focus were retained while painting disabled text in a readable theme colour instead of an illegible dark native disabled label. Settings and graph/list controls retain accessible names and native keyboard behaviour.

These changes address observed prototype issues. They are not proof that every primary/secondary workflow is screen-reader accessible or that OS high contrast/text scaling is accepted. High-contrast colour fallback exists but was not toggled/tested; reduced-motion animations are not delivered yet.

## Fresh verification

Dedicated Python QA environment: `.local/frontend-verify-20261003`; the owner's `.venv` was not replaced. Final-source commands/results before the documentation checkpoint:

- `./scripts/verify.ps1`: Ruff passed; mypy passed (255 source files at this invocation); generated contracts current; **685 Python passed, 25 opt-in skipped**; compileall passed; **8 PWA tests passed**. The skipped cases include native/hardware/model/voice acceptance and are not implied passes.
- `dotnet test clients/csharp_tests/csharp_tests.csproj`: **53 passed** (43 existing + 10 new test cases including parameterised contrast cases).
- `dotnet build clients/desktop_shell/desktop_shell.csproj`, `desktop_app/desktop_app.csproj`, `desktop_widget/desktop_widget.csproj`: **0 warnings, 0 errors** on the final prototype source.
- Ruff on the baseline/fixture scripts passed; source-inclusive mypy over `src` plus both scripts passed (139 files). An earlier standalone mypy invocation without `src` reported untyped imports; it was not counted as a passing run.
- All five original reference assets matched the manifest's byte lengths and SHA-256 values.

The main verification script now includes the two new scripts in Ruff/mypy checks. The subsequent final rerun after that integration and fixture-profile guard passed: Ruff, mypy **257 files**, current contracts, **685 Python passed / 25 skipped**, compileall and **8 PWA passed**; exit 0. Expected safety rejection of the previous nonempty profile was verified. A separate fresh final-source fixture on port 18797 returned all **84 fields**, **8 saved/active local switches false**, model state `down` and `dialogue_ready=false`, then shut down gracefully (exit 0). The first diagnostic assertion mistakenly expected a nested `saved` object; the real projection is flat field metadata with `value`/`active_value`, and the corrected assertion passed. This is an API/script smoke check, not additional GUI/model-load acceptance. No owner profile is an allowed default. Unity source was not changed and the Unity/hardware suites were not rerun in this turn.

## Framework decision and open gates

**Retain WinForms for the production GUI-1/GUI-2 implementation path**, using native accessible controls, explicit logical-pixel layout and custom lightweight painting where justified. The existing connected transport, 150% rendered probe, graph/list keyboard selection and model-independent recovery demonstrate a feasible path without a framework rewrite. This is a bounded feasibility decision, not acceptance of the prototype utility-tab appearance as the final supplied design.

GUI-0b remains **in review** pending explicit 100%/200% and mixed-DPI/text-scaling evidence, realistic large graph render/keyboard/zoom checks and screen-reader/high-contrast validation. Final-source connected conversation/graph replay and actual GUI Stop against the slow fixture are additional useful checks. Unit Stop tests cover protocol identity/cancellation but do not replace that GUI test.

Production remains to build: windowless profile singleton, owned/attached Core identity and graceful shutdown, one tray/coordinator, preference migration; the approved airy transcript/evidence chips/composer/attachments/IME/scroll behaviour; retained Activity/board/content/agent/paths and voice; full categorised Settings editor; real Memory services/relations and semantic host acknowledgements; actual scheduled Automations; final concept styling and ordinary launch/release acceptance. No prototype screenshot or regression count closes those gates.

Later same-day [GUI-1 host progress](GUI1_HOST_GPT-6.1-Sol_2026-10-03.md) supplies the opt-in attached host/identity/IPC foundation and actual GUI Stop evidence. That narrow delivered scope supersedes the corresponding earlier open-work statements here; managed services, full presentation/parity and GUI-0b accessibility/DPI review remain open. Final C# suite is 57; earlier 53-case count is retained as this original checkpoint's evidence.
