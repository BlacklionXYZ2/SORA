# File attachment and desktop vision repair — 2026-09-26

Recorded: **2026-09-26 16:54:44 +01:00 (Europe/London)**. Status: **implemented, in review**. This follows the full-system acceptance report's blocked widget attachment and missing capture-to-dialogue path; it does not supersede that report's other findings.

## Implemented behavior

- Owner-local dialogue accepts up to three selected local paths. The path need not be inside configured content/editor roots; the Windows account running Core must be able to read a regular local file. Paired remote sessions cannot use this path. Local file bytes/images are only dispatched to a loopback dialogue provider, never to a configured remote OpenAI-compatible endpoint.
- Text and DOCX extracts are bounded transient model context; supported image files become transient multimodal image parts in a Chat Completions request. Unknown/binary formats receive a bounded hex preview, not a claim of semantic understanding. Views are capped to protect model context and process memory. The original file payload is not saved as a message, although a model reply that quotes a file can be saved in chat history.
- The widget now has a paste-path fallback and posts structured file paths when sending chat. Its shell file picker runs on a separate STA thread so a stalled picker cannot block the widget message loop. The full app has an attach-file picker and path field. Delegated specialist tasks still use their existing bounded reference/compose path; this change concerns direct companion dialogue.
- The explicit **Look** / **Look at screen** controls ask for confirmation, query current physical monitor bounds from the DPI-aware Windows capture helper, issue an exact one-use, 30-second persisted desktop-observe grant, capture the display under the pointer, and send its PNG to the image-capable dialogue provider. The captured frame is removed from the volatile store after the turn; pixels are not written to message rows. Remote paired sessions cannot call this route. The deterministic fixture provider returns a configuration error rather than claiming visual understanding.

## Verification

| Check | Result | Boundary |
|---|---|---|
| `scripts/verify.ps1` | 359 Python passed, 10 opt-in skipped; Ruff/mypy/contract checks passed; 7/7 PWA checks | Repository gate, not a live vision model |
| `scripts/verify-desktop.ps1 -Native` | 66 passed, 1 elevated/inaccessible-app skip; native helper builds zero-warning | Owned Windows fixtures, not personal desktop interpretation |
| `dotnet test clients/csharp_tests -c Release --no-restore` | 33/33 passed | Includes structured attachment/desktop route payloads |
| `dotnet build clients/desktop_app -c Release --no-restore` and `dotnet build clients/windows_capture -c Release --no-restore` | Both succeeded, zero warnings | Source builds, not packaged-release sign-off |
| Native helper `--list-monitors` through Python bridge | Two physical displays and cursor display decoded successfully after fresh build | Read-only monitor topology query |
| New Core/API tests | Owner-local out-of-root file read, remote denial, image payload format, one-shot grant consumption, frame removal, no fake deterministic sight passed | Synthetic image/fixture capture |

## Outstanding live checks and setup

- The rebuilt widget was visually observed with its new **Look** button, but the computer-control service failed to activate that window twice. Per the UI test boundary, no click-through of Attach file or the new path fallback was claimed. The QA widget process was stopped.
- A local Gemma 4 vision model is installed, but two load attempts failed before inference with LM Studio's existing setting conflict: `V Cache Quantization requires flash attention to be enabled`. No LM Studio setting was changed. The temporary loopback server was stopped. The image payload was verified against a local mock Chat Completions server, not against this installed model.
- The normal deterministic dialogue backend cannot interpret screenshots. Configure a working local vision-capable OpenAI-compatible dialogue model, restart Core with the Windows capture helper configured, and then manually test **Look** on an intentionally non-sensitive screen. The capture helper and model availability are prerequisites; the code will return a clear error without them.
- This allows arbitrary *local* file paths, not UNC/network/device paths or files Windows denies to the Core process. For long files only a bounded excerpt is included per turn; PDFs and arbitrary binary formats are not semantically parsed yet. No automatic filesystem crawl or standing desktop observation was added.
- The broad path access is an explicit owner request and a privacy-sensitive trust expansion. Protect the owner API token and local model process; future remote/public access must not inherit these owner-local routes.
