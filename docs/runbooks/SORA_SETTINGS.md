# SORA Settings: GUI editing and model reload

Implemented 2026-09-28; change attribution: GPT-6 Astra (owner-requested label).

## Normal use — no JSON editing required

1. Close old clients/Core, then run `.\Start-SORA.ps1` to build and start the current version.
2. Open **Settings** in the full desktop application.
   Use **Go to section** to jump directly to Voice, Perception or Models. (In the native app, the section list is on the left.)
   Hover over a truncated label to read its full name and JSON key.
3. Under **Models → Brain (local model)**, use the **…** button beside **Brain model file (GGUF)** to select your model.
   SORA searches that folder for `mmproj*.gguf`. One candidate is filled automatically; multiple
   candidates open a chooser; none requires you to use the projector's **…** picker. The model
   and projector must match; filenames and GGUF headers cannot prove compatibility.
4. Edit the desired controls and click **Save settings**.
5. For rows labelled **On model reload**, click **Reload model** and confirm. Core stays running;
   new dialogue/voice generations wait for you to retry while the old turn drains and the model loads.
   Progress is shown as `reloading`, then `ready` or `down`. Loading can take minutes, not just seconds.

The three effect labels are:

| Label | Meaning |
|---|---|
| Immediate | Applies when saved. Access/perception changes invalidate in-flight evidence; ordinary timeout/provider values are snapshotted per turn. |
| On model reload | Saved now; applied by **Reload model**. Core and specialist state remain up. |
| Next SORA boot | Saved now; applied when you next stop and start Core. Model reload does not apply it. |

The page compares saved values with active values. Saving only an immediate setting does not create
a model-reload warning. Reverting a pending value clears that pending change. **Discard draft**
discards unsaved UI edits; it does not undo saved preferences. Reload is available for retry even
when no value changed. Unsaved drafts disable Reload so it cannot silently ignore them.

**View saved settings** shows a read-only, flattened view of the canonical preferences and the store
path. Secrets are not part of that file or view. The widget reports model reloading/unavailable;
editing stays in the full app for this update.

## Settings inventory

All keys below are exposed in the GUI. The store uses these nested groups:

| Group / keys | Effect |
|---|---|
| `local_companion`: native text, images, local files, interaction, avatar, delegation, voice and direct writing | Immediate; direct writing defaults off and does not install a writer |
| `perception.mode`: native-only, image-on-prompt, adaptive | Immediate |
| `perception.paused`, `perception.window_context`, `perception.desktop_context` | Immediate |
| `perception.interval_seconds`, `perception.context_max_age_seconds` | Immediate; adaptive timing/expiry |
| `dialogue.backend`: managed-llama, openai-compatible, deterministic | Next boot |
| `dialogue.timeout_seconds`, `dialogue.context_max_chars` | Immediate |
| `llama.executable`, `llama.port`, `llama.startup_timeout` | Next boot |
| `llama.model_path`, `llama.mmproj_path`, `llama.context_size`, `llama.gpu_layers` | Model reload |
| `llama.flash_attn`, `llama.cache_type_k`, `llama.cache_type_v` | Model reload |
| `llama.batch_size`, `llama.ubatch_size`, `llama.split_mode`, `llama.tensor_split`, `llama.main_gpu` | Model reload |
| `llama.cpu_moe`, `llama.n_cpu_moe`, `llama.load_mode`, `llama.swa_full` | Model reload |
| `llama.speculative.type`, `draft_model_path`, `draft_gpu_layers`, `draft_cache_type_k`, `draft_cache_type_v`, `draft_tokens_min`, `draft_tokens_max` | Model reload |
| `external.model`, `external.base_url`, `external.model_folder` | Next boot |
| `runtime.worker_count` | Next boot |
| `voice`: interpreter, Whisper directory, Kokoro ONNX/voice bank, microphone/speaker keys, voice name, recording limit and speed | Immediate; stops old voice worker, then Start voice loads the saved selection |

Context length is **tokens**; prompt budget is **characters**, a separate SORA context-compilation
limit. GPU layers supports `auto`, `all`, or a numeric count including zero. Flash attention supports
`auto`, `on`, `off`. The cache selectors offer the installed-build vocabulary; actual backend/model
compatibility is validated at load. Quantized V cache with flash attention explicitly off is rejected.

MTP is `draft-mtp`; DFlash is `draft-dflash` in the speculative mode selector. Draft modes require
a compatible draft GGUF selected in the GUI. Draft flags are omitted when no draft mode is selected.
These are not universal acceleration switches: a listed mode may not work with your model or
hardware. Core probes the installed runtime's advertised flags before stopping a working model,
then actual loading validates the pair. MTP was live-tested with this installed Gemma E2B and its
adjacent `mtp-gemma-4-E2B-it.gguf`: the request completed and the runtime reported 158 accepted draft
tokens out of 222 generated. This is a functional check, not a speed/quality benchmark. DFlash was
not live-tested. Start with **none** unless you have appropriate weights.

The typed configuration intentionally rejects arbitrary extra CLI arguments. RoPE overrides, CPU
affinity, tensor-name overrides and advanced n-gram tuning are not implemented settings in this
release (not hidden functional JSON-only controls). Authentication, loopback bind, one-slot server,
web-UI disabling and managed alias remain protected implementation choices, not editable controls.

## One authoritative store and migration

### Passive prompt context — 2026-10-02 update

**Perception** follows **Companion access** in Settings. In the default **native-only** mode,
ordinary local prompts receive bounded native window metadata and Desktop-directory file metadata
when their respective switches are enabled. These are listings, not automatic reads of all window
text or file contents. The model can request fresh native text/selection or bounded file reads.

**image-on-prompt** additionally supplies an ephemeral image of the recent application window,
when static native-observe/image access, the capture helper, a fresh application identity and a
loopback image provider are available. It does not substitute an entire display if that window
cannot be captured. Explicit attachments or an explicit screen image take precedence. Window
capture uses PrintWindow; some GPU/protected/minimized applications do not provide a useful image.
A configured helper/projector is not proof that the model understands images; test your pair.

**adaptive** captures the recent application window at a configurable minimum interval (default
30 seconds, range 5–300). Only changed image bytes or changed process/window identity invoke the
local model again. Core retains one bounded interpreted summary in memory, not a recording or
history of frames. Its maximum age is configurable (default 90 seconds, range 5–600), and matching
unchanged-image checks update the verification time without pretending to reinterpret the image.
Local prompts can use this timestamped context; if none matches/is recent, they take the normal
prompt-time image path. Native text/selection reads still take precedence over image guesses.

Chat and voice model generation preempt background refresh. There is no backlog of missed ticks.
Core cancels the background transport before admitting foreground inference; if cancellation has
not drained within two seconds, it returns a retry error rather than overlapping the two jobs.
Background interpretation has a 20-second-or-shorter deadline and cannot call tools, perform
effects, append conversation turns, delegate or remember. This is interval observation, not fresh
authority for a desktop action. Settings shows refresh state and the configured interval.

**Pause automatic perception** stops the foreground watcher and automatic prompt additions;
explicit read/look requests remain possible under the static access switches. Saving perception
changes invalidates in-flight automatic evidence and cancels background refresh. Application
switches, desktop/lock invalidation, provider replacement and shutdown discard background context.
This does not yet prove cancellation of every running foreground generation or desktop action.

The store is now version **6**. Valid version 2/3/4/5 stores migrate with a unique sibling backup,
retaining prior access/mode/pause choices and supplying missing generation-appropriate defaults.
Version 4 requires its original four perception fields; versions 5/6 require all six fields.
Version 6 also requires the complete voice field set. Missing access/perception/voice flags are
treated as malformed, not silently enabled. Older clients may submit older-version edits but
cannot display all new controls; rebuild. The 2026-10-03 repair makes the Windows projection
recognize version 6 instead of incorrectly showing the legacy LM Studio settings screen.

The unified file is `<state-root>/data/sora-settings.json`, normally
`.local/manual-test/data/sora-settings.json`. It contains both llama and Core preferences. Separating
state roots prevents QA instances from changing your normal configuration. Widget/window placement
preferences, identity, conversations, permissions and credentials are separate state, not model settings.

On the first run, Core imports the old runtime settings and selected legacy llama JSON, retaining
both original files untouched. After migration, the unified file wins; old `-DialogueModel` or
`-LlamaConfig` values no longer silently override your GUI choices. Change **Model source** and
external endpoint/model in Settings to use LM Studio again, then restart Core. No file renaming is
needed. `-Settings 'C:\path\sora-settings.json'` selects another store at launch; underlying CLI flag
is `--settings`. `config/sora-settings.example.json` is a template, not a valid model installation.

Writes are revision-checked and atomic. If the file changes externally, **Refresh from disk** reads
it before another Save. If that file is malformed, Refresh retains the last readable preferences;
Save backs up the malformed file to a unique `.invalid-*.json` sibling before replacing it. Invalid
settings at boot likewise leave the UI available for repair. Backups may contain private paths;
handle them like the main settings file.

## Failure recovery

If model loading fails, SORA tries the previous working model. A successful recovery shows **ready**
plus an explicit recovery/error message; the failed requested values remain saved and pending.
If recovery also fails, the model is **down** but Settings remains usable. Correct the settings and
retry Reload. A last-good model snapshot supports recovery on a subsequent boot without restoring
stale boot-only settings. The last-good file is a recovery snapshot, not another editable authority.

An occupied model port is never attached to as an unknown server. New requests receive an explicit
model-unavailable/reloading error rather than being sent to another provider. Authentication keys
rotate on reload and are never written to settings or projected in the GUI. Low-level diagnostics
stay in `<state-root>/logs/llama-server.log`; raw log tails are not embedded in the GUI because a
backend may log prompts or other private data. The GUI shows bounded failure/recovery messages.

## Verified and remaining manual checks

Verified through the native app: context 8192 → 4096, Save → pending, confirmed Reload → ready with
pending cleared; timeout 90 → 85 applied immediately with no reload warning; values survived a Core
restart. The final GGUF picker opened in the current model folder and selection populated the
adjacent projector successfully. Automated coverage includes projector discovery, migration,
disk-edit conflicts, malformed-file preservation, failed reload rollback and cancellation cleanup.

A separate real-model test reloaded Gemma 4 E2B IQ4_XS with flash attention **on**, K/V cache **q8_0**,
and 4096 context; SORA then answered **Red** and **Blue** for neutral-filename image fixtures.

Owner checks still valuable: try a different model pair, verify multi-monitor DPI/layout preferences,
and test DFlash only with compatible weights. Native multi-GPU/MoE
hardware, every cache format, and speculative speed/quality are not covered by the two image tests.
