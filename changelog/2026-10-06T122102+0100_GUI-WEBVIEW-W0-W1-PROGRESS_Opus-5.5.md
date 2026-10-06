# WebView2 rewrite: W0 web Chat spike and W1 foundation (opt-in)

Model name: **Opus 5.5**. Checkpoint **2026-10-06 12:21:02 +01:00**, Europe/London. Status:
**in progress**. W0 and W1 are built and component-tested; W0's gate needs the owner's machine.
It serves [V1.md](../V1.md) steps 2–6, because those steps are run from Chat. Plan:
[GUI_WEBVIEW_REWRITE_2026-10-06.md](../docs/plans/GUI_WEBVIEW_REWRITE_2026-10-06.md).

Before starting, at the owner's request, the pre-rewrite state (`main` at `993cbe1`) was kept on
branch **`snapshot/winforms-gui-2026-10-06`** for later comparison. The matching tag was created
locally, but the push was refused by the connection, so the branch is the record.

## Changes

- **W1 design system** (`clients/panels/shared/`):
  - `tokens.css` holds colours, glass layers, glow, radii, spacing, type and motion taken from
    `02-chat.jpg`, `05-settings.jpg` and design v0.1. `--font-ui` is the one font token (Segoe UI
    Variable until the owner chooses).
  - `base.css` and `components.css` provide window chrome, cards, tiles, chips, status, buttons,
    inputs, toggles, category rail, banner, toast, avatars and resize grips.
  - `icons.js` holds static line icons. `api.js` makes same-origin Core calls with no token in
    the page. `bridge.js` is the typed host message list, and `window.js` wires the title bar,
    dragging, resizing and the host's backdrop report.
  - `gallery/` is a component gallery page for review.
- **W0 web Chat** (`clients/panels/chat/`):
  - It shows the conversation from Core and polls every 2.5 s, so voice turns and agent reports
    appear.
  - Send works with Enter, Shift+Enter makes a new line, and IME-safe Enter is respected.
  - While SORA answers, Send becomes **Stop** (`/api/v1/dialogue/cancel`). A draft that Core did
    not record is restored.
  - Status and alert lines are shown as Core's notes, not as SORA's words.
  - The microphone button opens the existing Voice window.
  - Message text is only ever set as text, never as HTML.
- **SoraShell host** (`clients/desktop_shell/`):
  - `WebPanelForm` is a borderless window with a shared WebView2 environment. Pages are served
    from `panels\` under the virtual host `panels.sora.example`, with navigation pinned to it,
    and with no new windows, context menu, reload or zoom unless `SORA_PANELS_DEVTOOLS=1`.
  - Translucency has two routes, chosen with `SORA_PANEL_BACKDROP`: the Windows 11 system
    backdrop (default) or composition accent blur. It falls back to solid glass when Windows
    transparency is off, and reports the route it used to the page.
  - `PanelApiProxy` forwards the page's same-origin GET and POST calls under `/api/v1/` to the
    loopback Core with the owner token and Core identity. Everything else is refused, and failures
    become honest 503 responses.
  - `PanelBridge` validates every page message (window actions, an allowlist of panels to open,
    and resize edges) and drops anything else.
  - `ShellHost` uses the web Chat only when `SORA_PANELS=web`. The WinForms Chat is unchanged and
    remains the default.
  - The WebView2 package is 1.0.4258.31. Its WPF assembly is excluded at build time to keep
    builds warning-free.
- **Launcher and tools:**
  - `Start-SORA.ps1 -WebPanels [-PanelBackdrop System|Accent|None]` (PowerShell 5.1-safe).
  - `scripts/capture-panel.ps1` captures the panel on screen, blur included, beside its concept.
  - `scripts/panels-dev-server.py` previews panels in a browser, following the same forwarding
    rules as the C# proxy.
  - `scripts/verify-panels.ps1` is now part of `verify.ps1`.
- **Docs:** a new "Trying the new web Chat" section in `HOW_TO_USE.md`; the plan status, the
  `V1.md` GUI line, and a new owner check list `docs/gui/W0_OWNER_CHECKS_2026-10-06.md`.

## Verification (fixture, component and browser render; nothing native)

- `node --test clients/panels/tests/panels.test.mjs`: 10 passed. They cover page logic, the
  same-origin API with no token, unreachable versus refused errors, the bridge allowlist and the
  icons.
- **Real Core in this container** (deterministic model, isolated state in
  `.local/panels-qa-2026-10-06/`) through the dev server, in headless Chromium:
  - Chat sent two turns. Shift+Enter kept the draft and Enter cleared it after sending.
  - The replies appeared, with no page errors.
  - With Core down, the banner showed, Send was disabled and the draft was kept.
  - The forwarder refused DELETE and path traversal.
- **Render review:** I compared screenshots of the gallery and Chat with `02-chat.jpg`. The layout,
  glass tiles, accents and chips match closely. In a browser there is no real blur, only a
  stand-in gradient.
- `dotnet test`: 380 passed / 16 failed. The 16 are the existing Windows-only failures; the 27 new
  `WebPanelTests` (bridge, forwarding, token handling) all pass. The Shell host builds with 0
  warnings and 0 errors.
- `pytest tests/test_panels_dev_server.py`: 7 passed. `tests/test_launcher_powershell51.py`:
  passes (no `ArgumentList`). `ruff`: clean.
- **Not run:** WebView2 itself, real blur, DPI, speed, IME, `capture-panel.ps1`, and the launcher
  on Windows. All of these are in the owner's check list.

## Limits and next

- If the web Chat has a turn in flight, Quit does not wait for it (the WinForms Chat did).
  Core still cancels the turn on shutdown.
- W2 (Chat parity: attachments, chips, history anchor) and W3 (Settings from field metadata) are
  next, after the owner's W0 report decides the translucency route.
