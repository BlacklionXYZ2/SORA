# File attachment and desktop vision repair — GPT-6

Model name: GPT-6

Status: **implemented / in review at 2026-09-26 16:54:44 +01:00 (Europe/London)**. This is a repair to existing companion capabilities, not a declaration that a roadmap phase or live acceptance is complete.

- Added owner-local, read-only access to any regular local file readable by the Core Windows account, independent of configured content roots. Added bounded text/DOCX/binary views and transient image input to the direct dialogue provider; paired remote sessions and non-loopback dialogue endpoints cannot receive these files.
- Changed widget chat attachments from path-only/inline preview composition to structured file selection handled by Core. Added paste-path fallback, moved the shell picker off the widget UI thread, and added a full-app attach-file picker/path field.
- Connected explicit desktop-view controls to current monitor discovery, an exact one-use persisted observe grant, native screenshot capture, and transient multimodal dialogue. Deterministic dialogue now refuses to imply it saw pixels.
- Added Python owner/remote/file/image/grant/frame tests and a C# request-routing test. Final checks: repository 359 passed / 10 opt-in skipped plus 7/7 PWA checks; native desktop 66 passed / 1 skipped; C# 33/33; relevant builds zero-warning. See `docs/verification/FILE_AND_DESKTOP_VISION_REPAIR_GPT-6_2026-09-26.md` for evidence and limitations.

Open review: live GUI click-through could not run because the Windows control service could not activate the widget; installed local vision models could not load due to an existing LM Studio cache/flash-attention setting conflict. No claim is made that a real model has yet described a captured personal screen.
