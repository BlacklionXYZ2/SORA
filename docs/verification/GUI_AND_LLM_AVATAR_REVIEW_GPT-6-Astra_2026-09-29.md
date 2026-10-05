# SORA GUI and LLM-to-avatar review

Review attribution: **GPT-6 Astra** (owner-requested changelog name).
Live GUI tests: **2026-09-28, approximately 19:43–19:52 BST**.
Continuation / evidence review: **2026-09-29 08:05 BST**.
Review and QA cleanup completed: **2026-09-29 08:07:52 BST (UTC+01:00)**.
Status: **review completed; recommendations not implemented**.

## Scope and method

Used the Computer Use skill and native Windows UI automation to navigate the full desktop app,
exercise its five companion pose buttons, send three real-model chat requests, inspect Settings,
Content and Integrations, open the attachment picker, and create/assign a note in the expanded board.
Also inspected the running compact widget. Backend reads and source inspection were used to
corroborate UI results, not as substitutes for clicking the controls.

Profile: `.local/settings-qa-20260928`, Core port 18773, managed llama.cpp port 18771.
Dialogue used the installed Gemma 4 E2B IQ4_XS GGUF with its projector and the QA profile's MTP
configuration. These tests did not use a paid specialist model or dispatch any specialist task.
Normal `.local/manual-test` conversations/settings were not used for these test interactions.
The startup script built the capture helper, full desktop app and widget successfully, each with
zero warnings/errors. No full regression suite was rerun for this review-only task.

## Main conclusion

**The avatar's manual presentation controls are wired up, but direct chat does not have a general
LLM-to-avatar action path.** This is an integration gap, not evidence that Unity cannot accept poses.
Automatic thinking/idle reflects runtime activity; it is not an LLM choosing and executing a gesture.

| Test | Live result | What this proves / does not prove |
|---|---|---|
| Wave button | Unity-reported `waving` | UI → Core → renderer state path works; rendered motion quality not assessed |
| Sit button | `sitting` | Pose state received, not verified seat contact |
| Lean button | `leaning` | Pose state received, not verified physical support |
| Climb pose button | `climbing` | Pose state received, not climbing/traversal |
| Stand / reset | `idle` | Manual reset reaches renderer |
| Chat: ask to wave with the 3D avatar | Refused; sampled idle → thinking, then idle | Natural-language wave not executed |
| Chat: ask to sit, explicitly saying this is only an avatar pose | Refused; sampled idle → thinking → idle | Clarifying virtual intent does not provide a command path |
| Chat: move avatar 100 pixels right | Refused; final position remained x=90, y=300 | Requested movement did not occur |
| Open/expand board | Compact note board expanded into three columns | Basic board presentation works |
| Add QA note / assign Hermes | Note saved; colour changed yellow → purple; no agent started | Assignment and colour presentation work |
| Drag note toward In Progress | No movement | Drag/drop is absent in inspected form code; explicit move controls exist but were not exercised to completion |
| Activity after assigning Hermes | Still showed specialist `unassigned` | Assignment vs actual execution backend are poorly distinguished |
| Attach file | Native picker opened; Escape cancelled | Picker open/cancel only; file parsing/inference not retested here |
| Compact widget | Showed same conversation, Ready to talk, 0 runs | Shared conversation projection works |

### Exact chat probes and responses

1. `Please wave to me with your 3D avatar now, then tell me whether the movement was actually performed.`

   SORA: `I am unable to perform physical actions such as waving with a 3D avatar. I do not have the necessary authorization or capability for that type of interaction.`

2. `Sit down using your 3D companion body. This is only an avatar pose, not a physical-world action. Tell me if you can send that command.`

   SORA: `I am unable to perform physical actions, even avatar poses, as I do not have the necessary authorization or capability for that type of interaction.`

3. `Move your 3D avatar 100 pixels to the right. Then explain in about 100 words which avatar controls you can actually execute and whether this movement occurred.`

   SORA explicitly said movement did not occur. It also described vague programmatic/GUI QA abilities;
   this is model-generated prose, not evidence those actions are executable.

### Why chat cannot currently do this

- `src/sora/runtime/service.py:1267`: the direct-dialogue capability registry registers task-status
  reading, not companion pose/movement commands.
- `src/sora/runtime/service.py:1400`: dialogue has bounded file/board paths, then calls the provider
  and stores its textual response. It does not parse/dispatch avatar action requests.
- `src/sora/providers/dialogue.py:151` and `:193`: active capabilities are not exposed as callable
  tools; Chat Completions is called with model/messages/stream=false, without tool schemas/results.
- `src/sora/embodiment/local_player.py:121`: thinking/waiting/idle is selected by a runtime watcher.
- `clients/desktop_app/FullAppForm.cs:182`: manual pose buttons call `/api/v1/companion` directly.

The correction is a bounded semantic-action interface, not granting the language model unrestricted
renderer or OS control. Existing exact-scope authority and presentation/OS-effect boundaries should
remain intact.

## Prioritised criticisms and improvements

| Priority | Observed issue | Recommended improvement / acceptance criterion |
|---|---|---|
| P1 | Chat cannot execute even the harmless avatar poses available as buttons | Add typed `set_pose`, then bounded `move_to` / `look_at` actions. Expose only currently available/authorised actions. Report success only after correlated renderer feedback. Test chat wave/sit/move end to end, including disconnected renderer and invalid targets. |
| P1 | Full-app attachment button is vertically cropped; compact widget labels/hints also clip | Replace conflicting fixed heights with DPI-aware auto/minimum sizing. Check 100%, 150%, mixed-monitor DPI, default/minimum/maximised layouts and keyboard focus. The full-app attachment clipping persisted when maximised during this test. |
| P1 | Chat stays in the composer until the complete reply; only a footer says Working; Send remains visually enabled | Show the submitted message immediately, add inline thinking/progress, disable or clearly queue conflicting actions, provide cancellation, and stream responses. Preserve a new draft typed while another response is pending. |
| P1 | Avatar failure recovery requires restarting SORA | Add Restart avatar, Show/Hide, Re-centre, current monitor and renderer health controls. Restart only the renderer, retaining Core/conversations/model. Explain loading vs disconnected vs not configured. |
| P2 | Settings is a very long technical form; at default size the large fixed header leaves roughly five rows visible | Use Basic/Advanced sections, compact persistent Save/Reload bar, field help and search. Put GGUF/projector/context/GPU first; advanced batch/MoE/speculative options behind clear groups. Keep effect-tier and pending-change labels. |
| P2 | Internal vocabulary is exposed: `managed-llama`, `Ubatch`, `Cpu moe`, `Swa full`, raw paths | Use friendly labels with technical names in tooltips; show model filename plus full-path hover/copy. Explain compatibility and resource tradeoffs without promising speed gains. |
| P2 | Content requires an exact reference and a manually pasted grant ID | Present file/folder names and an ordinary user-authorisation workflow. Keep grant identifiers in technical details. This recommendation does not remove checks or broaden filesystem authority. No permissions were changed in the review. |
| P2 | Integrations shows raw component/capability IDs and says the Kanban component is disabled while a board is usable | Separate registered extensions, built-in features, enabled status and runtime health. Explain why an integration is unavailable and which user action resolves it; keep implementation IDs secondary. |
| P2 | Board is note-like, but operations are detached dropdown/buttons; dragging does nothing | Add drag/drop and per-card assignment/context controls with keyboard equivalents. Keep run status distinct from board placement and make selection obvious. |
| P2 | Board says Hermes assigned, Activity says unassigned | Show separate Assigned agent and Running backend, or `Hermes · not started`. `FullAppModel.cs:62` currently displays effective_backend, while board uses assigned_agent. The underlying distinction is valid; the presentation is misleading. |
| P2 | Widget shows `hermes` beside Ready to talk even though local Gemma is the dialogue model | Label dialogue model separately from available specialists. Current `WidgetForm.cs:481` chooses the first available specialist, not the answering model. |
| P3 | Screens are largely empty grids/transcript text with equal-weight controls and weak empty states | Keep conversation primary; give Send a clear primary style, move advanced task controls into a secondary menu, add helpful empty states, readable message grouping and inspectable provenance. |
| P3 | Avatar page is mostly empty and loading another VRM requires a CLI argument | Add avatar preview/identity, VRM picker, scale/position controls, motion preference and last-action feedback; keep advanced diagnostics collapsible. |

Draft-loss note: source clears `composer` after awaiting the previous reply (`FullAppForm.cs:657`).
This is a plausible race if a new draft is entered during generation. The attempted live race was
inconclusive because the reply finished before the replacement draft was entered. **Not counted as
a reproduced defect.** The busy UI and lack of inline progress were directly observed.

## Recommended implementation order

1. LLM → typed avatar action → validated Core dispatch → renderer acknowledgement. Start with
   existing poses; add movement only with topology-aware bounds and visible cancellation.
2. DPI/layout and chat-busy/draft handling; shared model/specialist/assignment terminology.
3. Avatar lifecycle controls and actionable failure states.
4. Settings organisation, attachment chips and guided Content/Integration workflows.
5. Board direct manipulation and companion-first visual refinement.

Keep renderer animation quality as a separate acceptance track. Better motion alone will not fix
the missing chat command interface. Explicitly distinguish requested, accepted, started, completed,
failed and cancelled actions; a state enum or an HTTP `queued` response is not completion proof.

## Limits and continuation observations

- The transparent Unity overlay did not appear in Computer Use's targetable app/window inventory.
  Renderer telemetry reported visible=true during live pose tests, but no independent screenshot
  of the avatar was available. Gait, wave quality, clipping, feet/contact, gaze, lip sync and drag
  behaviour of the actual 3D body remain **visually unverified**.
- On 2026-09-29 the QA API still responded, but `/api/v1/companion` reported running=false,
  visible=false, disconnected, with `The 3D companion closed. Restart SORA to open it again.`
  The cause of closure was not diagnosed; do not call this a proven crash or timeout.
- Fresh Computer Use captures after the overnight pause were inconsistent with the selected
  window/accessibility tree. Those images are excluded from product-defect evidence. Successful
  2026-09-28 observations above remain the basis of the UI critique.
- No new model-reload/cache/MTP benchmark, paid-agent task, voice/microphone, phone/PWA,
  permission-grant, deletion or broad desktop-vision test was performed in this review.
- The QA note and conversations are retained only in the isolated QA profile as evidence.
  No application-source fixes or roadmap completion claims are part of this review.
- At completion, the QA-scoped Core launcher/runtime and both QA desktop clients were stopped;
  a fresh process check found zero remaining processes with this QA profile. Other SORA profiles,
  LM Studio and unrelated model servers were not stopped.
