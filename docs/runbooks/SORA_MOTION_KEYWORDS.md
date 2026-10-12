# SORA: small-model motion keywords

Implemented 2026-09-29. This is a first keyword prototype, not a parameterised motion controller.

## Current native look / point addition — 2026-10-03

The unified local companion-call path now supports `look` and `point` at a native control found
through `list_windows` then `inspect_window` (`controls`). These additions are implemented and
fixture/integration-tested; real-model and visible GUI acceptance remain open. They do not add
clicking or typing. The older keyword-only implementation below is retained as historical context;
its file/image exclusion and grant description apply to that legacy path, not the current static
owner-policy companion path.

After loading the new Core source and a rebuilt player, try in local Chat:

- `Please point at the Pause button in <the application's window title>.`
- `Please look at the search box in <the application's window title>.`
- Negative check: `Don't point at Pause; just tell me where it is.`
- With a selected text file: `Summarize this note, then point at Pause in <window title>.`

Keep native desktop reads and avatar presentation enabled in Settings, with the observation
helper and renderer connected. No per-action permission application is needed. Do not restart
an existing session unexpectedly: these source changes do not hot-update a running Core, and the
isolated QA player build does not replace the normal installed player.

The model-facing effect has only an operation and a turn-local reference, for example:

```json
{"op":"point","target":"t1234abcd-c1"}
```

The reference above is illustrative, not usable: Core issues fresh opaque references only for
eligible inspected controls, and only references actually shown in the bounded model context
can be selected. The model cannot supply native window handles, coordinates, authorization or
success claims. Core checks the original request, static policy, target/process identity, current
geometry, topology and cancellation before dispatch. Quoted/file/control text is not authority.
Unknown, expired, disabled, off-screen or stale targets produce a truthful failure, not a second
effect or guessed coordinate.

`look` means avatar gaze; it does not mean image capture or reading pixels. `point` runs the
renderer reach/retract lifecycle without a desktop press/type effect. The chat receipt confirms
dispatch only. Correlated renderer completion is stronger presentation evidence, but still does
not prove visual quality or that anything in the desktop application changed. Ambient chat-state
restores are held while this presentation is in progress so finishing the reply does not cancel it.

See [checkpoint evidence](../verification/W3_NATIVE_PRESENTATION_GPT-6-Astra_2026-10-03.md) for
test scope and the remaining real-model, native-application and visible-animation checks.

## Try it

Restart SORA with `./Start-SORA.ps1` so Core loads the updated Python code. Keep the 3D companion
enabled and use your local managed llama.cpp model. In the normal Chat tab, send one of:

- `Could you sit down please?`
- `Lean your avatar to one side.`
- `Show your climbing pose.`
- `Stand up again.`
- `Come here.` / `Walk to my pointer.`
- `What can you see on my screen right now?` (one-shot screen look; needs the capture helper and a
  vision-capable dialogue model)

She has no wave: the `wave` keyword only walked her on the spot and was removed on 2026-10-12
at the owner's request. To make her walk, ask her to walk or come here.

No manual pose-button click is needed. Core responds that it sent the pose request, not that the
animation finished. The 3D companion tab reports the renderer's state. Sitting/climbing are poses,
not seat contact or physical traversal. Stand/reset returns the avatar to idle.

## The entire model-facing call

```json
{"motion":"sit"}
```

| Keyword | Existing renderer state |
|---|---|
| `sit` | `sitting` |
| `lean` | `leaning` |
| `climb` | `climbing` |
| `stand` | `idle` |
| `walk` | one `move_to` command to the pointer location: Core samples the cursor (capture helper) and supplies the destination; the renderer's placement policy may adjust the spot so her full footprint stays on the display |
| `none` | No pose command; continue ordinary conversation |

The generated public schema is `contracts/schema/v1/motion-choice.schema.json`; the source of truth
is `src/sora/contracts/motion.py`. Only `motion` is accepted. Extra properties, coordinates, grant
fields, free-form action strings and unknown keywords are rejected.

Core makes a short classification call to the same configured dialogue model. It sends only the
current owner message and a compact instruction/example set, not conversation history or file/screen
contents. The model chooses the keyword; this is not a regex mapping of human phrases to commands.
One validated choice can produce at most one pose dispatch. For `none`, a normal conversation call
follows, so ordinary chat with a configured avatar has one extra small-model classification call.

The llama.cpp adapter requests schema-constrained JSON, temperature 0, a 64-token output cap and
non-thinking output. It follows the project's [official Pydantic/JSON schema example](https://github.com/ggml-org/llama.cpp/blob/master/examples/json_schema_pydantic_example.py).
Core validates the result again. It does not repair arbitrary text into an executable action.
Other OpenAI-compatible servers must support this constrained-output form; compatibility beyond the
tested installed llama.cpp build is not claimed. Invalid/unsupported output fails closed.

## Boundaries

- Only owner-local text dialogue with a configured `LocalAvatarSession` and a motion-capable
  dialogue provider enters this path. Remote paired chat cannot trigger it.
- File/image turns skip motion selection. Embedded instructions in attachments cannot call it.
- Core, not the model, supplies the renderer state, command ID, timestamp, topology and session
  authority. The existing persisted `embodiment.command` grant is still validated.
- No model-supplied movement coordinates, speed, duration, joint angles or autonomous idle planning
  are added by this feature. `walk` moves the avatar to one Core-chosen destination (the owner's
  pointer when the capture helper is available, otherwise the cursor monitor's centre).
- Thinking/waiting can temporarily interrupt a requested pose; the selected resting pose is restored
  afterwards. It is not automatically converted to a timed animation. Use Stand/reset to end it.
- While a walk is in flight, pose restores are deferred: a projection push mid-walk re-anchors the
  renderer and used to cancel the walk. Travel ends on arrival (client-reported position within 60 px)
  or after 20 s, then the resting pose is restored.
- Dispatch is not completion proof. The prototype does not implement command-correlated animation
  completion feedback or claim visual correctness from a state enum.
- This first path is text-chat only. The separate microphone/voice pipeline is not motion-enabled.

## Can SORA inspect the desktop, windows and files just by being asked?

The bounded native/file read loop is available in local chat as of 2026-10-02. Desktop effects
are still separate and not a general multi-step action loop. Current interfaces are:

| Request | Current behaviour |
|---|---|
| Ordinary chat: `What can you see on my screen right now?` | Explicit screen requests can capture the display under the cursor with static image access and a local vision model. Ordinary prompts add no automatic images in native-only mode; image-on-prompt adds only the recent application window. |
| **Look at screen** | Explicit, one-shot capture of the display under the cursor, sent to the local vision model. Matching projector required; this is not continuous monitoring. |
| Ask about a particular window | Local chat can enumerate windows and inspect current native controls/text/selection using static access and the observation helper. The normal one-command launcher wires it. Prior-application identity survives clicking SORA, but must still match a fresh inventory. |
| Attach a local file | Bounded read of the selected file; supported images are passed to the vision model. |
| `read file C:\path\file.txt` | The existing narrow local-file command reads that explicit path. `view`, `inspect`, and `summarize` in the same command form are also recognised. |
| Find and inspect a file | Bounded list/search/read tools can discover an unattached local file, with Desktop-directory metadata as optional prompt context. Arbitrary spreadsheet/PDF semantic extraction is not yet provided. |

Local file paths are not restricted to workspace/content roots: the reader uses this Windows
account's access to regular local files. This is not support for every file format or unlimited
context. Text/DOCX/images have bounded representations; binary files may only yield a hex excerpt,
and arbitrary PDF/spreadsheet semantic extraction is not provided by this generic reader. Remote
chat cannot read owner-local files, network paths are excluded, and file/image content goes only to
a loopback dialogue model. At most three selected files/images enter a turn.

The separate bounded read vocabulary is now implemented, with observations returned as untrusted
data and truthful unavailable/error results. The unified chooser can request an enabled read and
then one presentation/delegation effect; read permission itself does not authorize an effect.
Native conversational press/type executors and Core-owned verification, real-model/GUI acceptance
and more general targets remain subsequent work.
