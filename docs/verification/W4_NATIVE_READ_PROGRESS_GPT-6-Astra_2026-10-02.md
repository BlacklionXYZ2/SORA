# W4 native reads — implementation and user-side evidence

Contributor: GPT-6 Astra. Foundation slice completed **2026-10-02 12:40:18 +01:00**.
Overall W4 and the full frontend goal remain **in progress**.

## Delivered

- Compact, validated `list_windows`, `inspect_window`, `list_files`, `search_files`, `read_file`
  and `finish` calls. Models cannot add authority, shell commands, writes or arbitrary verbs.
- Cross-process visible-window inventory, process-start identity, bounded native UIA document
  text and selected text. Read-only inspection does not focus, click, type or scroll.
  Document text reads also include exposed selection; selection-only reads remain available.
  Password-control names/text are redacted. Pattern availability is separate from empty text.
- Owner-local conversation orchestration with at most six decision steps, one invalid-call
  repair, repeated-call detection, a conversation deadline, bounded valid-JSON observations,
  and a settings epoch recheck before and after reads and before answering from their data.
- Automatic compact user/Public Desktop directory metadata. File bodies are not automatically
  ingested. Absolute local paths are not restricted to the project or attachment list.
- Paged listings and literal name/text searches, bounded text/DOCX views, opaque transient
  references, cursor validation and changed-file checks. Scans avoid recursive directory
  reparse loops; cancellation/revocation stops further scan work between filesystem operations.
- Native/file observations appear in local replies with operation, source, outcome and timestamp.
  Screenshot and motion selectors are not run after a targeted read in this foundation slice.
  Native observation remains available with screenshots or avatar control disabled.
- Local read context is not enabled for remote sessions or hosted non-loopback dialogue models.
- Ordinary `Start-SORA.ps1` now reaches a manual-start script that builds and supplies the
  native observation bridge. Previously that path supplied capture only.
- The managed dialogue header uses the actual loaded GGUF filename rather than `sora-local`.
  Companion access controls are ordered first in Settings, ahead of advanced model controls.

## Fresh verification

| Check | Evidence and scope |
|---|---|
| Full repository verification | `scripts/verify.ps1`: **513 passed, 14 opt-in skipped**, 76.86 s; Ruff, mypy over 222 files, contract freshness, compileall and **7 PWA tests** passed |
| Final static checks | Ruff, mypy and contract freshness passed again after the final native-test assertion update |
| C# regressions | **36 passed**, `dotnet test clients/csharp_tests/csharp_tests.csproj --no-restore --nologo` |
| Builds | Windows observation helper, UIA fixture and isolated full desktop application built with zero warnings/errors |
| Native helper | Opt-in owned-window test passed: inventory identity, document text, selection `bef`, password redaction, three-character combined budget, zero fixture clicks/text changes |
| Real local-model selected-text integration | Final API/Core/native/llama.cpp fixture passed twice, 13.74 s and 12.19 s; final assertion requires the exact word `bef`, a native inspection evidence line, and unchanged fixture state |
| Launcher wiring | PowerShell parser accepted the edited launcher; regression checks its build/argument wiring. A full ordinary-launch lifecycle is **not** proven by this syntax check |

Native integration can be rerun after building the helper/fixture using `SORA_TEST_UIA=1` and
`pytest tests/desktop/test_native_reads.py`. To include a real model, also supply
`SORA_TEST_READ_API` (a loopback isolated Core URL) and `SORA_TEST_READ_TOKEN_FILE` (its owner
token file). That opt-in appends a test conversation to the specified Core, so use QA state,
not personal history. Never print the token.

## GUI and real-model review

Computer Use inspected the full Windows application and submitted real prompts through its
composer and Send button. The test model was **Gemma 4 E2B, `gemma-4-E2B-it-IQ4_XS.gguf`**, with
its explicit `mmproj-F16.gguf`, managed by llama.cpp on port 18785. Core used port 18784 and
`.local/native-read-qa-20261002`. No paid specialist was invoked. No owner SORA settings or
personal conversation database were changed.

Cleanup: the QA Core and its managed llama.cpp child were stopped after the final tests;
ports 18784 and 18785 were verified no longer listening. Test records and fixtures remain
under the isolated `.local` folder for inspection; no personal test history was deleted.

1. **Window listing — GUI passed with a discovered limitation.** “List the titles of currently
   open windows using native Windows information, not a screenshot.” produced native window
   titles and a `windows.win32` evidence line. No capture helper was configured in this QA Core.
   The first view lost some inventory entries to context compression. Repairs shortened default
   Desktop previews, removed model-unnecessary geometry, prioritized fresh observations and
   added an explicit visible-top-level count/scope. Complete-list GUI acceptance after those
   repairs remains open. Inventory deliberately includes helper/untitled windows, not just apps.
2. **File discovery/read — GUI passed.** With the attachment field empty, asked SORA to find the
   note mentioning `quiet-blue-orchid` under the isolated fixture folder and report its time.
   She issued `list_files` then `read_file`, selected `travel-note.txt`, and correctly answered
   **16:45 on Friday**, with filesystem evidence. She was not given the target filename.
3. **Selected text — initial GUI failure, subsequently repaired and API-verified.** The native
   helper exposed `bef`, but the initial model answer claimed no selection. Follow-up exposed
   three contributing problems: an ambiguous/default inspection mode, context pruning that
   could drop useful control data, and reuse of stale assistant claims in answer history.
   Inspection mode is now explicit; document reads carry selection; selected/document text is
   a top-level result field; newer data survives older metadata; and fresh read answers omit
   historical assistant observation claims. The corrected live response explicitly identified
   selected text **`bef`** and full text **`before`**. One run also attempted an unknown reference
   and received `stale`; it did not gain broader access or perform an action. The final corrected
   path has **not yet been rechecked through the GUI** because the QA windows had closed.
4. **Header/layout — observed and improved.** The reopened app showed the actual GGUF filename.
   The transcript/evidence was readable. The Settings page exposed separate native-read and
   screenshot switches, but buried them below GPU options; field ordering was repaired.
   The new top placement still needs a rendered recheck. No access switch was clicked: the
   Computer Use skill forbids changing in-app security/privacy settings. Policy changes were
   exercised in isolated automated tests instead.

## Remaining work; not implied complete

- Corrected selection and complete inventory GUI rechecks; common real applications, not just
  the owned WinForms fixture; empty/unsupported/elevated/window-reuse matrices; mixed DPI.
- Preserve the last non-SORA foreground/selection when chat takes focus; passive native context
  and prompt-time/hybrid imagery; interval scheduling, lock/pause and inference prioritization.
- Follow-up reference/context continuity and mixed attachment/read/action turns. Current read
  orchestration runs on plain owner-local turns; attachments retain their existing direct path.
- Replace independent decision chains with the broader unified action/delegation schema. This
  read-only slice suppresses later motion/screenshot selection after a targeted read, so mixed
  requests and automatic pixel fallback after unsupported UIA are not yet complete.
- Format adapters: PDF/spreadsheets and arbitrary binaries are explicitly unsupported as text;
  new text tools do not return image bytes. Existing attachment/image support remains separate.
  Search is best-effort (depth 8, at most 10,000 visited entries and 64 KiB text prefixes);
  it is not an exhaustive full-drive/content index. Network paths/cloud-only placeholders and
  OS-inaccessible objects remain technical limitations, not per-file permission requests.
- User-side cancel/pending-turn presentation, clearer capability availability, full settings
  render/restart/recovery acceptance, and reconciliation of all launchers/helpers.
- W2 model/tool catalogue, full agent routing/paths, W3 broader interaction, W5 real Windows
  voice and W6 lifecycle/proactivity remain tracked by the full frontend checklist.

This evidence supplements, rather than replaces, the existing owner manual acceptance checklist.
