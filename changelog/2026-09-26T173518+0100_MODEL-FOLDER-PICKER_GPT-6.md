# LM Studio model-folder selection — GPT-6

Model name: GPT-6

Status: **implemented at 2026-09-26 17:35:18 +01:00 (Europe/London); live model inference in review**.

- Added an owner-local model scan that matches LM Studio's indexed GGUF LLMs to files inside an entered models directory, reports display name/key/size/vision metadata, and rejects network paths and catalog paths outside the selected folder.
- Added a persistent model-folder field and model choices to full-app Settings. Choosing a listed model stages its LM Studio key through the existing versioned save/restart flow; Core rechecks membership before saving. Legacy manual model-key settings continue to work without a folder.
- Added API and C# projection/payload tests, plus a user-facing tryout guide update. The complete gate passed: 361 Python tests and 7 web checks; 10 opt-in Python skips; 33 C# tests; zero-warning desktop build. Evidence and live limitation are recorded in `docs/verification/MODEL_FOLDER_PICKER_GPT-6_2026-09-26.md`.

Open: this machine's LM Studio vision-model load-setting conflict still prevents a live selected-model answer. A configured LM Studio server with JIT loading or a preloaded model is required; SORA does not import or execute arbitrary GGUF files from the folder.
