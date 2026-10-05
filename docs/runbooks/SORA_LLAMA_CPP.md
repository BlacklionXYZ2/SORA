# Standalone local vision with llama.cpp

> **Superseded setup instructions, 2026-09-28:** model and runtime preferences are now editable in
> the full app's **Settings** page. The first run migrates the legacy llama JSON and runtime settings
> into one `<state-root>/data/sora-settings.json`; subsequent edits use that file. Use **Save settings**
> then **Reload model** for model-tier changes. You no longer need to edit JSON or rename files to
> switch backends. See [current Settings instructions](SORA_SETTINGS.md). The material below records
> the earlier standalone-loader setup and remains useful only for legacy import and flag background.

Implemented and live-verified on 2026-09-28. SORA can own a local `llama-server`
process without LM Studio. It always supplies both `--model` and `--mmproj`;
the projector is required and must match the model architecture/version.

## This computer

The machine-specific configuration is `.local/llama-server.json` (ignored by Git).
It selects the existing `C:/llama.cpp/llama-server.exe` and these installed files:

```text
C:/Users/oscar/Desktop/Models/Unsloth/gemma-4-E2B-it-IQ4_XS-GGUF/gemma-4-E2B-it-IQ4_XS.gguf
C:/Users/oscar/Desktop/Models/Unsloth/gemma-4-E2B-it-IQ4_XS-GGUF/mmproj-F16.gguf
```

No models or runtimes were downloaded. The tested executable reports
`0.2.0-dev`, build 1, commit `e85caa8`. Use a llama.cpp-compatible server that
supports this model architecture and the flags below; older binaries may not.

Close any previous SORA clients and stop their Core before starting again:

```powershell
.\Start-SORA.ps1
```

The launcher auto-detects `.local/llama-server.json`, loads the model and
projector, waits for the authenticated model endpoint, then starts Core and the
desktop client. LM Studio does not need to be open or listening. Existing chat
history and non-model settings are retained. Other model servers are not stopped
automatically; close/unload them yourself if GPU memory is tight.

To select a different local pair, edit the three paths in the JSON and restart
Core. Use forward slashes or escaped backslashes in JSON. Relative paths resolve
from the configuration file's directory. `config/llama-server.example.json`
is a portable template, not an installation-specific working configuration.

```powershell
.\Start-SORA.ps1 -LlamaConfig 'C:\path\local-model.json'
```

## Parameters and lifecycle

The managed command is equivalent to:

```text
llama-server.exe --model <model_path> --mmproj <mmproj_path> --host 127.0.0.1
  --port 18771 --alias sora-local --ctx-size 8192 --parallel 1
  --gpu-layers auto --no-webui
```

JSON options are `executable`, `model_path`, `mmproj_path`, `port`,
`context_size`, `gpu_layers`, and `startup_timeout`. The supplied setup uses
8192 context tokens and a 180-second startup timeout. `gpu_layers` accepts
`auto`, `all`, or 0–999 (0 keeps language-model layers on CPU; projector/backend
offload behavior remains runtime-specific). Unknown arguments are rejected.

SORA generates a per-launch model API key and passes it through the child
environment, not command-line arguments or the settings file. It strips
inherited `LLAMA_*` options and the known conflicting `LLVM_PATH` from that
child only; the parent/system environment is unchanged. The server binds only
to loopback and the web UI is disabled. An occupied model port fails startup;
SORA does not attach to an unknown process or silently switch back to LM Studio.

The configured model takes precedence over persisted LM Studio model settings.
In desktop Settings, model/backend/endpoint/folder edits are disabled while this
mode is active, with a startup-configuration explanation. Other settings remain
editable and do not overwrite the saved external-model choice. The LM Studio
folder scanner is for external mode only; standalone model/projector selection
currently happens in this JSON, not a GUI picker.

Ctrl+C in the Core terminal also stops its managed model server. A pipe-watching
supervisor closes the model process if Core is forcibly terminated. Closing
only a desktop client leaves Core and its model running, as before.

## Optional external server and direct CLI

An explicit `-DialogueModel` bypasses automatic standalone configuration:

```powershell
.\Start-SORA.ps1 -DialogueModel 'YOUR-EXTERNAL-MODEL-ID'
```

Existing saved Settings continue to take precedence in external mode. Update
them if needed. Do not supply both `-DialogueModel` and `-LlamaConfig`.
Alternatively, move/rename `.local/llama-server.json` to restore the legacy
LM Studio auto-detection path. Nothing modifies LM Studio's own overrides.

The underlying Core CLI can also be used directly:

```powershell
uv run --locked sora --root .local/manual-test --identity-root identity `
  --llama-config .local/llama-server.json --dialogue-timeout 90 --serve
```

That direct command does not add the launcher's desktop capture helper, avatar,
or specialist/workspace configuration; use `Start-SORA.ps1` for those.

## Verification and troubleshooting

Live verification used SORA's authenticated dialogue API and two generated
256×256 images, both named `image.png`. Answers were `Red` and `Blue` for the
respective pixels. Unauthenticated model access returned 401. Clean shutdown
released the model port; an independently launched QA Core was also forcibly
stopped and its model process exited. This proves local image interpretation,
not a fresh complete desktop screenshot/OCR or full GUI acceptance pass.

Repeat the opt-in hardware test from PowerShell (it loads an additional model
on a free port; stop other model instances first to avoid memory pressure):

```powershell
$previousTestConfig = $env:SORA_TEST_LLAMA_CONFIG
try {
    $env:SORA_TEST_LLAMA_CONFIG = (Resolve-Path .local/llama-server.json).Path
    uv run --locked pytest tests/providers/test_managed_llama_server.py -k live -s -q
} finally {
    $env:SORA_TEST_LLAMA_CONFIG = $previousTestConfig
}
```

Startup/backend diagnostics are appended to `<state-root>/logs/llama-server.log`
(normally `.local/manual-test/logs/llama-server.log`). Treat logs as private:
backend versions may include paths or request details. Missing files, malformed
config, unsupported GGUF architecture, insufficient memory, or mismatched
projector should be corrected before retrying. GGUF header validation alone
cannot prove projector compatibility; real inference does.
