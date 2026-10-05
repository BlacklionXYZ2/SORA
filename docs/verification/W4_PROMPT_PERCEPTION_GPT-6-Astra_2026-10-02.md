# Prompt perception / prior-application GUI evidence

Author: **GPT-6 Astra**. Slice completed **2026-10-02 23:00:16 +01:00**.
The frontend goal remains active; this record closes a bounded implementation slice only.

## User-side result

Computer Use activated the owned `SORA UIA acceptance fixture` (field `before`, selection `bef`),
then the isolated SORA full application. Submitted question:

> What is selected in the application I was using before opening this chat? Use native Windows
> text, not a screenshot. Answer in one sentence.

The GUI's canonical transcript showed:

> The selected text in the "SORA UIA acceptance fixture" window was "bef".

Provenance: native inventory **2026-10-02T21:51:13+00:00**, UIA selection
**2026-10-02T21:51:18+00:00**. The Ready-to-talk header named the actual local
`gemma-4-E2B-it-IQ4_XS.gguf`. A shortened-context warning remained visible; this is not evidence
of complete window coverage. No screenshot was needed. Fixture evidence remained
`press_count=0`, `text_change_count=0`, `text_value="before"`.

A read-only Settings scroll exposed native-only mode, pause, window/Desktop metadata and Immediate
badges. No access/privacy controls were changed through Computer Use. The screenshot exposed
empty status lines and overconfident image wording; both were repaired and rebuilt. The second
app launch was rejected by execution policy; post-polish visual reinspection remains open.

## Implemented behavior and boundaries

Version 4 settings and original-file migration backups were tested, including live save, restart,
malformed flags, policy-epoch changes and preserved model display name. Native metadata is bounded
and automatic only when enabled; it is not a read of all window/file contents. Native-only adds no
automatic images. Pause stops automatic additions and foreground watching; explicit reads/look
remain available under static access. Remote requests do not inherit these owner-local additions.

Image-on-prompt captures only the recent application's identity with native PrintWindow. Identity,
timestamp, PNG and budgets are validated; policy checks bracket capture and result delivery.
There is no full-display fallback, focus change, desktop-frame insertion or action-target authority.
Explicit images/attachments take precedence. GPU/protected/minimized windows can fail or be blank.
Raw images are transient; model answers can quote contents and are stored in conversation history.

Actual native-window capture plus local Gemma/projector inference passed: the model answered
`before` from the owned fixture image, without clicks or text changes. This is component evidence,
not automatic-mode GUI acceptance. Both Windows clients' explicit Look paths now use static image
access without a separate capture-approval dialog; that button interaction needs a fresh GUI test.

## Verification and reproduction

Full regression before final status/example polish: **528 passed / 16 opt-in skipped**, 67.97s;
7 PWA checks; Ruff, mypy 226 files, schema freshness and compilation checks passed. After final
changes: settings/local-policy/perception **31 passed / 2 opt-in skipped**; final perception-only
**7 passed / 1 opt-in skipped**; targeted Ruff/mypy and schema freshness passed. C# **36 passed**;
full-app build zero warnings/errors.

The opt-in image test creates its own synthetic fixture, dynamically allocated model port and
random in-memory credential, supplies only that window image, and closes children in `finally`.
**1 passed in 8.01s**; image answer measured **2.84s**, not a general performance benchmark.

```powershell
uv run --locked pytest tests/runtime/test_perception.py tests/runtime/test_app_settings.py tests/runtime/test_local_policy.py -q
$env:SORA_TEST_PERCEPTION_MODEL_CONFIG = 'C:\Users\oscar\Desktop\SORA\.local\native-read-qa-20261002\llama.json'
try {
    uv run --locked pytest tests/runtime/test_perception.py::test_native_application_image_with_local_model -q -s
} finally {
    Remove-Item Env:SORA_TEST_PERCEPTION_MODEL_CONFIG
}
dotnet test clients/csharp_tests/csharp_tests.csproj --no-restore
```

Requires installed native helpers and the local model/projector; no weights were downloaded and
no paid provider used. GUI state stayed in `.local/native-read-qa-20261002`, not owner history.
Owned QA processes stopped and ports 18784/18785 cleared; logs/state retained.

## Next gates

Adaptive/hybrid change-aware intervals, bounded scheduling and conversation priority; complete
lock/in-flight generation cancellation; image-on-prompt GUI acceptance and final layout recheck;
widget/real-editor handoff, normal startup/restart, broader files/mixed effects and every remaining
workstream in the [active tracker](FRONTEND_ALIGNMENT_TRACKER_2026-10-01.md). No unsupported adaptive
entry is offered in the current selector.
