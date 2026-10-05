# Explicit projector loading through managed llama.cpp

- Author/model: GPT-6 Astra
- Completed: **2026-09-28 09:01:01 BST (UTC+01:00)**.
- Status: **implemented and verified** for standalone loading and image inference.
- Scope: user-requested alternative to LM Studio's disabled projector defaults.
  This does not declare a new roadmap phase or full desktop acceptance complete.

## Changes implemented

1. Added `src/sora/providers/llama_server.py`: validated local JSON configuration,
   required separate GGUF/model-projector files, explicit `--model`/`--mmproj`,
   loopback bind, model alias, context/GPU settings, readiness timeout, busy-port
   rejection, and per-launch authentication. Inherited llama options and the known
   conflicting LLVM_PATH are removed from the child only. A pipe-based supervisor
   stops the child when Core closes or dies. Backend output goes into the state's
   `logs/llama-server.log`.
2. Added `--llama-config` to Core and `-LlamaConfig` to both launchers. The manual
   launcher auto-detects `.local/llama-server.json`, unless an external
   `-DialogueModel` is explicitly supplied. The outer launcher allows up to eleven
   minutes for build/startup (configuration loading itself is bounded to 600 seconds).
3. Managed model settings override saved LM Studio selection. Saving unrelated
   settings preserves that external selection and never persists the generated
   model API key. Model switching via runtime settings is rejected in managed mode.
4. Added a `dialogue_managed` projection flag. Desktop Settings disables incompatible
   model/backend/endpoint/folder edits, explains startup-config ownership, skips the
   LM Studio scanner, and restores editing when external mode returns.
5. Added a portable `config/llama-server.example.json` and ignored local configuration
   selecting installed `C:/llama.cpp/llama-server.exe`, Gemma 4 E2B IQ4_XS and its
   matching `mmproj-F16.gguf`. LM Studio configuration and model files are unchanged.
6. Added lifecycle/configuration/persistence tests and an opt-in real-model test;
   extended the C# projection test for old/new managed flags. Added
   `docs/runbooks/SORA_LLAMA_CPP.md` and updated the local tryout instructions.

## Verification completed

- `scripts/verify.ps1`: Ruff, mypy (197 source files), generated-contract freshness,
  compileall, **377 Python tests passed / 11 opt-in tests skipped**, and **7 PWA tests
  passed**. The hardware model test is included among normal-suite skips and was
  separately run below.
- `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet`:
  **34 passed**, including managed/legacy settings projection assertions.
- Full desktop app and widget compiled to isolated `.local/llama-client-check`
  output directories: zero warnings/errors. Both launcher scripts parsed cleanly.
- Real installed server reports `0.2.0-dev`, build 1, commit `e85caa8`.
- QA Core on port 18772 launched its server on 18771. The inspected server command
  included the exact projector; the log reported a loaded multimodal model.
  Force-stopping that QA Core also removed its owned model process.
- Opt-in test via `SORA_TEST_LLAMA_CONFIG`: **1 passed** in 13.09 seconds. Two
  generated 256×256 images with neutral `image.png` paths produced **Red** and
  **Blue** through SORA's actual dialogue API. Unauthenticated model requests
  returned 401; clean shutdown released the listening port.
- Test processes were cleaned up. Independent Hermes/LM Studio servers were left
  untouched. The normal UI session was not restarted as part of this change.

## Remaining boundaries

- Next normal SORA start activates the ignored local configuration. Close old
  clients and stop any existing Core first. No model/runtime download was needed.
- Standalone model/projector paths are selected in JSON, not a new GUI picker.
- Image inference is proved, but this change did not repeat full GUI interaction,
  desktop capture/OCR, avatar, or native-action acceptance. Existing opt-in native
  tests were not re-run. Broader model quality/performance is not established by
  two color-image checks.
- All pre-existing/concurrent checkout edits and attribution records are preserved;
  no source-repository commit was created.
