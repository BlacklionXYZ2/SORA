# Voice, Agents, Project paths, Memory and Appearance as glass web windows

Model name: **Opus 5.5**. Checkpoint **2026-10-12 17:34:06 +01:00**, Europe/London. Status:
**implemented and component-tested; checked in headless Chromium against an isolated Core only.
W5's gate is not passed**: nothing here has run in SoraShell on Windows, and the owner has not
reviewed the look. This moves stage W5 of the
[WebView2 rewrite](../docs/plans/GUI_WEBVIEW_REWRITE_2026-10-06.md) forward. The plan lists W5 as
"after V1"; the owner asked for it directly on 2026-10-12 ("Go ahead with W5 for now"). It touches
V1's "Presence and GUI host" row (the Voice and Agents windows) but changes no V1 step's result
until it is checked natively.

## Changes

1. **Five new web pages** in `clients/panels/`, each a model module with no DOM (tested) and a
   view, styled like Chat, Settings and Activity. They replace the WinForms windows at parity with
   the same safety rules; the old windows still open with `-ClassicPanels`.
   - **Voice** (`voice/`): microphone and voice state (never shown as closed unless the worker
     says so), the dialogue model, Hold to talk (mouse or Space, pinned to one voice instance;
     losing focus, hiding or losing the pointer throws the recording away), Start voice, Stop
     speaking, Stop voice response, Close audio worker, and the device list Core last reported
     with duplicate keys flagged. Polls every 2.5 s, or 10 s while hidden.
   - **Agents** (`agents/`): the catalogue under SORA's names, each agent's models and
     capabilities, Refresh models (35 s limit), and model purposes saved through Settings with the
     revision check. Starting a task asks for confirmation first, uses one idempotency key per
     attempt, never retries by itself, offers **Retry exact submission** or **Discard attempt…**
     when the outcome is unknown (only a definite 400 `INVALID_INPUT` releases the key), and links
     the receipt to Activity.
   - **Project paths** (`paths/`): reserved project folders and recent write evidence, with
     Core's own caveat shown as-is, a confirmed **Recheck stopped writers**, stale-data labels and
     a check that Core's instance has not changed.
   - **Memory** (`memory/`): Overview and Search (Graph is shown as "not yet"), filters, cursor
     paging, a validated detail with evidence (**Open** follows Core's reference), **Correct** and
     **Forget** with confirmation, acknowledgement checks (SHA-256 of the content), receipt
     lookup, exact retry and review. The semantic highlight works with the host: the host keeps
     the lease, poll and acknowledgement, and the page selects the record and reports its anchor.
   - **Appearance** (`appearance/`): text size, reduced motion, Chat shortcut, compact and pinned
     Chat, technical detail and **Reset panel placement**, saved by the host with a baseline
     check ("Keep my edits" on a conflict) and the read-only and recovery states.
2. **Host** (`clients/desktop_shell/`):
   - `PanelBridge` parses the new page messages: `panel.busy`, `prefs.save` (exactly the seven
     appearance values, each range-checked), `prefs.reload`, `prefs.recover`, `placement.reset`
     (each with a request ID), `memory.presented` (a GUID request ID, a status and an anchor in
     CSS pixels) and `memory.highlight-cleared`.
   - `WebPanelForm` posts host messages only once the page is ready, applies text size as the
     WebView2 zoom, reports geometry changes, converts the Memory anchor to screen pixels (DPI and
     zoom), and names the panel in its fallback text.
   - `ShellHost` opens all five as web windows by default, sends `host.preferences`,
     `host.core`, `host.result`, `host.present-memory` and `host.presentation-outcome`, refreshes
     after a page's Core change, and counts web panels' unsaved and in-flight work in the quit
     prompt (naming the window).
3. **Shared page code** (`clients/panels/shared/`): new Core calls (agents refresh, delegate,
   paths, memories, content references, identity, companion); IDs go into paths through
   `itemPath`, which refuses anything but an exact ID; `CoreError.detail` keeps Core's error
   object; `hostRequest`, `validAppearance`, reduced motion through `data-motion`, a `graph`
   icon, and shared styles (danger buttons, state pills, inline confirmations, data tables).
4. **Links between windows:** Settings → Models has **Agents and their models…** and **Project
   paths…** buttons, Settings → Appearance opens the Appearance window, and each memory Chat
   used has **Show**, which opens Memory on that exact record.
5. **Review fixes** (a separate read-only review of the host and bridge found no serious bugs):
   - only the Appearance window may save, reload or recover preferences or reset placement;
     any other window gets a refusal;
   - SORA's memory request no longer reports "already visible" for a window the host had to
     show, and a highlight that changes after the page reports it is not confirmed;
   - a request to show a memory waits while Voice, Agents or Project paths are sending
     something, as it already did for the classic windows;
   - a reloaded or crashed page no longer leaves Quit blocked by work it reported (a crashed page
     reloads itself);
   - Memory opened by SORA's request now loads its list afterwards and keeps the record it shows
     selected.
6. **Documents:** HOW_TO_USE.md (the glass windows section, quit protection, screenshot titles,
   known limits), the plan's status header and the roadmap's current-position line.

## Verification

| Kind | What | Result |
|---|---|---|
| Component (JS) | `node --test tests/*.test.mjs` in `clients/panels`: new Paths 17, Appearance 14, Voice 28, Agents 21, Memory 25, plus shared API and bridge cases; `node --check` on every page module | 140 passed, 0 failed |
| Component (C#) | `dotnet test clients/csharp_tests/csharp_tests.csproj` (Linux, `EnableWindowsTargeting`), including the new bridge cases | 403 passed, 17 failed: the same Windows-only lifecycle tests that fail on this Linux machine without the change (they start `powershell.exe` or `cmd.exe`); all 48 web panel tests pass |
| Build | `dotnet build clients/desktop_shell/desktop_shell.csproj -p:EnableWindowsTargeting=true` | 0 warnings, 0 errors |
| Fixture (browser) | Headless Chromium with `page.route` fixtures for states the isolated Core cannot produce: Codex/Hermes catalogue rows, voice devices and a held microphone, preference conflicts, 409 and 503 responses, a Recheck result | Each page's flows exercised; screenshots at 1000×700 and about 620×600 |
| Live API (isolated) | A seeded QA Core in `.local/w5-qa-2026-10-12/` through `scripts/panels-dev-server.py`. All nine pages load at both sizes with no page errors and no horizontal overflow. Agents started tasks with the `deterministic-mock` agent only; Memory corrected `memory-bulk-53`, `-55` and `-56` and forgot `-52` and `-54` | Passed |

The only console errors are Voice's and Chat's 403 "Local audio is owner-local only": Core refuses
owner-local voice calls from this Linux container (`is_owner_local()` is false here), so the
Voice page shows "Microphone status UNKNOWN" honestly.

**Not run:** SoraShell with WebView2 on Windows (the native check), real audio, real Codex,
Hermes, Aggie or Claude, `scripts/verify.ps1` and pytest (no Python changed), and
`scripts/capture-panel.ps1`. The host's review fixes in `ShellHost` and `WebPanelForm` build
cleanly but have no unit tests (they need WinForms and WebView2) and have not run.

## Limits and next

- **The native check on Windows** decides the gate: open each window from the tray and command
  menu, hold to talk in Voice, have SORA show a memory (the highlight lines up with the record at
  125% and 150% scaling), change text size and reduced motion, quit with unsaved work in each
  window, and capture each against its concept (Memory against `04-memory.jpg`).
- **Forget's wording** says the saved moment (pictures, recording and what was said) is deleted.
  That matches Core: `routes.py` calls `forget_entry`, which removes the memory's entry folder.
  The classic window's text ("Private captures follow existing retention") predates that.
- **Follow-ups not done:** a shared lock so two windows cannot change Core at once; a
  `host.window` visibility message (pages use `document.hidden`); Chat's press-to-talk could
  reuse Voice's `HoldToTalk`; optional abort signals on the remaining API calls.
- The note board, Content, Integrations and the command menu are still WinForms.

HOW_TO_USE.md: updated.
