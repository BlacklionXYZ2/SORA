# Glass Settings window, a better web Chat, and both as the default

Model name: **Opus 5.5**. Checkpoint **2026-10-07 13:00:00 +01:00**, Europe/London. Status:
**built, component-tested, and checked natively in an isolated profile. The owner has not used
it yet.** This moves the [WebView2 rewrite](../docs/plans/GUI_WEBVIEW_REWRITE_2026-10-06.md)
stages W2, W3 and W4 forward, and V1's "Chat window and Settings window" row. The owner asked:
"Could you work on the gui actually? It would be nice to get that working."

## What changed

1. **New web Settings** (`clients/panels/settings/`, stage W3).
   - **Generated from Core's settings projection.** Every one of the 129 fields appears under its
     category, group, type and effect tier. There is no hand-made list to fall out of date.
   - **Models follows concept 05:**
     - a card showing the model SORA is actually using (its active value), with Loaded, Loading
       or Not loaded, any model error, and "saved for the next reload" when that differs;
     - information tiles, using only values Core reports, with no invented VRAM figures;
     - the captured llama.cpp arguments, with a copy button.
   - **Change model** opens the native file picker. It then finds the vision projector beside
     the model (`/models/projectors`), and the save bar offers **Save and reload model**.
   - The agent colleagues are folded away per agent, under the names SORA uses (Cody, Aggie).
   - **Saving** sends only the edited keys with the revision the page read.
     - A conflict keeps the owner's edits, re-reads and asks them to save again.
     - Model-tier changes offer the reload, and restart-tier changes say so.
     - "File changed outside SORA" offers to load it.
     - Ctrl+S saves.
2. **Web Chat** (stage W2, partly):
   - SORA's replies get a safe subset of formatting: paragraphs, lists, headings, bold, code and
     code blocks, built only from text nodes, so no HTML in a message ever runs;
   - Core's evidence footers ("Automatic window image…", "Read evidence", "Background window
     context…") become chips that open to show the detail;
   - attachments: the paperclip picks up to three files and sends them as `file_paths`. A message
     that fails to send keeps its text and attachments.
3. **Host:**
   - The bridge has a typed `file.pick` message (`gguf`, `exe`, `dir`, `file`, `attachment`, with
     a safe request ID). The host answers with the chosen path only.
   - `ShellHost` opens any panel that has a web page (now Chat and Settings) as a `WebPanelForm`,
     sized per panel.
4. **Default switched (stage W4):**
   - `Start-SORA.ps1` now opens the web Chat and Settings. `-ClassicPanels` brings back the
     WinForms ones, and `-WebPanels` is still accepted.
   - The shell treats anything except `SORA_PANELS=classic` as web.

## Verification

| Kind | What | Result |
|---|---|---|
| Component (JS) | `node --test` panel tests: Settings logic (all fields reachable, conversion, exact change sets, rebase after conflict, honest tiles, file-pick validation), Chat formatting and evidence | 21 passed |
| Component (C#) | `csharp_tests`, including new `file.pick` bridge cases | 401 passed |
| Build | `desktop_shell` | 0 warnings, 0 errors |
| Fixture (full) | `scripts/verify.ps1`, whose test runs include the panel tests | 1019 passed, 25 skipped, 4 xfailed; mypy clean on 310 files; PWA 8/8; panels 21/21 |
| Live API | Isolated QA Core (E2B) through the panels dev server, using the page's own modules. Steps: save context 4096, check that a stale-revision save is refused (`SETTINGS_CONFLICT`), reload the model (3.8 s), restore 8192, reload again | Passed |
| Native | Isolated SoraShell in `.local/gui-qa-20261007` attached to the QA Core | Details below |

What the native check showed:
- With no `SORA_PANELS` set, Settings opened as the web page
  (`https://panels.sora.example/settings/index.html`).
- **Real blur of the desktop** showed behind both windows.
- Driven through the WebView's debugging port, a live setting was toggled, saved (it became
  active at once) and reverted, and the save bar cleared.
- Screenshots are beside the concepts in `.local/gui-qa-20261007/native/`.

## Not done or not verified

- **Not tested:** the native file dialog. Only its message validation is tested. Change model
  was tested by API, not by clicking.
- **W2 still lacks** activity chips for agent tasks, memory chips, and voice state on the
  microphone button.
- **No warning on quit:** unsaved Settings drafts are not reported to the host, so quitting SORA
  discards them.
- **Still WinForms:** Voice, Activity, Agents, Paths, Memory and Appearance (stage W5).
- **Still open:** the owner's look review and W4's week of daily use.

HOW_TO_USE.md: updated (Change model flow, the glass windows section, `-ClassicPanels`).
