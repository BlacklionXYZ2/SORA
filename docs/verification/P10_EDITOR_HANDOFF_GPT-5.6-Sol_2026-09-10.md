# P10.4 Contextual Editor Handoff Verification

- Model: GPT-5.6 Sol
- Completed: 2026-09-10 19:55:30 +01:00 (Europe/London)
- Status: P10.4 complete; P10.1 remains in review; P10.5–P10.7 and overall P10 remain open
- Foundation: GPT 6 Astra's P10.1 Windows observation bridge and GPT-5.6 Sol's P10.2–P10.3 target/presentation boundary

## Delivered boundary

P10.4 uses a configured cooperating-editor integration because UIA does not reliably expose repository roots, canonical file paths, dirty-buffer state or exact text selections across editors. `POST /api/v1/editor/tasks` accepts structured app metadata, but Core does not treat it as verified until an exact persisted `path.read` grant has been resolved and consumed.

Core independently checks:

- the absolute repository root is configured through `--editor-root` or the managed Codex repository;
- the resolved repository-relative path remains within that root;
- the target is a bounded UTF-8 regular file of at most 2 MiB;
- the current saved bytes match the editor's document SHA-256;
- the one-based, end-exclusive Unicode-code-point selection resolves inside the file;
- the exact canonical-LF selection matches the editor-reported text, bounded to 4,096 characters;
- the capture is no more than 60 seconds old; and
- the associated volatile desktop target belongs to the same owner, device and project.

The verified `EditorContextSnapshot` is persisted inside the task under ordinary task retention. Its repository, file, range, document digest, selection digest and JSON-escaped selected text enter the deterministic provider context ahead of conversation history. If that block cannot fit the configured context budget, the run fails rather than silently omitting it. Trace fields record identifiers, hashes and line bounds, never selected text or the repository path.

Editor tasks are local-only in this initial privacy boundary. A cloud provider cannot be selected merely because its name appears in the request; a later explicit provider-disclosure policy may broaden that boundary without changing selection verification.

Completed normalized results may contain typed `EditorFinding` values bound to the context ID and selection digest. `POST /api/v1/tasks/<task-id>/editor-finding` rejects missing, failed, unrelated or invented results/findings. For an accepted finding, Core consumes a fresh exact Level 1 presentation grant, reruns target revalidation and maps the finding's selected line range to a proportional marker band inside the current selection rectangle. It does not focus the editor, move the pointer, change the selection, click, type or invoke UIA.

## Fixture acceptance

`tests/desktop/test_editor_handoff.py` uses a real temporary UTF-8 file and a deterministic cooperating-editor payload. It proves that the exact `beta\ngamma\n` range reaches both the persisted task and the provider request, including the repository-relative file and both digests. The provider returns a typed finding for the second selected line; after the target moves, the queued marker covers the recalculated second line band.

The same fixture proves that a changed document hash, guessed selection text and unconfigured repository are rejected. An invented finding absent from the completed provider result queues no command. The route-level fixture verifies typed submission/finding responses and rejects incomplete metadata.

This is a deterministic app-integration fixture. It does not claim a packaged VS Code, Visual Studio, Rider or other editor extension. The already accepted native P10 target fixture continues to cover real WinForms/UIA identity and rectangle presentation.

## Commands and results

### Focused editor fixture

```powershell
uv run --locked pytest tests/desktop/test_editor_handoff.py -q
```

Result: **3 passed**.

### Native desktop gate

```powershell
.\scripts\verify-desktop.ps1 -Native
```

Result: both .NET projects built with zero warnings/errors; **23 tests passed in 4.56 seconds**.

### Repository gate

```powershell
.\scripts\verify.ps1
```

Result:

- Ruff passed.
- Strict mypy passed over 130 source files.
- Published schemas were fresh.
- Pytest: **235 passed, 3 skipped in 21.54 seconds**; the skips were the explicit native UIA, .NET transport and packaged Unity opt-ins.
- Compileall passed.

### Native-enabled full suite

```powershell
$env:SORA_TEST_CSHARP = '1'
$env:SORA_TEST_UIA = '1'
uv run --locked pytest -q
```

Result: **237 passed, 1 skipped in 24.20 seconds**. The only skip was the separately opt-in packaged Unity player already covered by Astra's P09 evidence.

## Remaining limitations

- P10.1 still needs Astra's live inaccessible/elevated-application matrix.
- The initial editor ingress accepts clean saved UTF-8 buffers only; dirty buffers are rejected through digest/selection mismatch rather than guessed.
- A production editor adapter/extension has not been packaged.
- P10.5 volatile cursor/gesture capture, P10.6 conversational references and P10.7 configured navigation remain open.
- P09.4 physical display/power transitions remain open independently.

No commit, tag, editor mutation, focus change, pointer injection or UI semantic action was performed.
