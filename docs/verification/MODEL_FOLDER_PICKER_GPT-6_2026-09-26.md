# LM Studio model-folder picker verification — 2026-09-26

Recorded: **2026-09-26 17:35:18 +01:00 (Europe/London)**. Status: **implemented; live selected-model inference remains in review**.

The full Windows app Settings now accepts a local **LM Studio folder** path. **Scan models** asks owner-local Core for LM Studio's indexed GGUF LLMs whose files actually exist beneath that exact directory, then offers their display names, model keys and reported vision capability. The user can select a key, save a versioned settings revision, and restart Core to activate the direct dialogue choice. Manual model-key entry remains available when no folder is configured. SORA does not move/copy model files, change LM Studio's own models directory, or silently select another model.

Core normalizes and stores the chosen folder path without reading weights. A selection made with a folder is checked again against LM Studio's current catalog before staging; missing/unindexed keys are rejected. The scan route is owner-local and absent from paired remote access. A missing folder during a later restart does not prevent Core from starting; the model request itself may still fail until the owner fixes the path/model. LM Studio must run its local server with JIT loading enabled or have the selected model already loaded. No new SORA model runner was added.

## Checks

| Check | Result | Scope |
|---|---|---|
| `scripts/verify.ps1` | 361 Python passed, 10 opt-in skipped; Ruff/mypy/contract checks and 7 PWA checks passed | Whole repository gate |
| `dotnet build clients/desktop_app -c Release --no-restore` | 0 warnings/errors | Full-app compilation |
| `dotnet test clients/csharp_tests -c Release --no-restore` | 33/33 passed | Includes folder payload and pending-settings projection |
| New API tests | Indexed file offered; absent, embedding and traversal catalog records excluded; wrong model rejected; owner-local and remote boundaries; saved folder/key activate after restart | Synthetic catalog and temporary GGUF fixture |
| Local CLI smoke | `lms ls --json` responds; scan of default `~/.lmstudio/models` returns zero matching models on this machine | Does not identify the machine's custom LM Studio models directory |

The current local LM Studio vision-model load attempts previously failed with a V-cache quantization/flash-attention configuration conflict. This pass did not change that external setting or prove a live model inference after selection. The user should copy the directory shown in LM Studio's **My Models** tab rather than assume the default `~/.lmstudio/models` path.
