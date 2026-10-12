# Web Chat fixes found on the owner's machine: port, API forwarding, capture script

Model name: **Opus 5.5**. Checkpoint **2026-10-06 21:17:20 +01:00**, Europe/London. Status:
**fixed, and checked natively in isolated QA profiles**. This moves the W0 gate of
[the WebView2 plan](../docs/plans/GUI_WEBVIEW_REWRITE_2026-10-06.md) forward. The W0/W1 work in
`6c810af` was built in a Linux container, without WebView2. Its native check on the owner's
machine failed as shown in the owner's screenshots.

## Causes and fixes

1. **No SORA Core started; every panel showed "Core returned 404" or "not reachable".**
   - Port 8765 is held by Antigravity's own server on this PC. The native-app branch of
     `Start-SORA.ps1` passed `--core-url http://127.0.0.1:8765` *before* the existing fallback to
     a free port, which only the old Desktop branch reached.
   - The shell probed 8765, attached, and got a 404 from Antigravity's identity route. It then,
     correctly, refused to start a second Core on an occupied port, so no Core ran at all.
   - Fix: before the native app starts, the launcher reuses the port saved in the profile's
     `desktop-shell/runtime.json` (`core_url`). Otherwise it uses the first free port in
     8765–8775 and says so.
2. **The web Chat could never reach Core**, even on a free port.
   - `SetVirtualHostNameToFolderMapping` makes WebView2 serve that host internally, so the
     `/api/*` request filter never ran.
   - Proven from inside the page through the debugging port: `/chat/index.html` returned 200
     and `/api/v1/status` threw "Failed to fetch".
   - Fix: there is no folder mapping. SoraShell answers the whole panel host itself. `/api/v1/`
     goes through `PanelApiProxy`, as before, and files come from the new
     `clients/desktop_shell/PanelFiles.cs`: GET only, known types only, nothing outside the
     panels folder, with encoded traversal refused.
3. **`scripts/capture-panel.ps1` failed on Windows PowerShell 5.1.**
   - Its title "SORA · Chat" was non-ASCII in a file without a byte-order mark, so it was
     misread. The title is now built with `[char]0x00B7`.
   - It passed `$null` to `FindWindow`, which PowerShell turns into "" (a class name). It now
     passes `[NullString]::Value`.
4. **Not a code fault: the panel is solid, not see-through.** Windows' **Transparency effects**
   setting is off on this PC (`EnableTransparency = 0`). The host correctly reported no backdrop,
   so the page used solid glass. The owner's setting was not changed; this is documented in
   HOW_TO_USE.md.

## Verification (native, owner's machine, isolated QA profiles)

- With Antigravity still on 8765: "Port 8765 is used by another program; SORA will use 8766",
  and Core was healthy on 8766 within about 12 s. The saved-port read returns 8766 from the
  profile's real `runtime.json`.
- In the page: `/api/v1/status` and `/api/v1/messages` return 200, panel files return 200, and
  traversal returns 404.
- A message typed into the web Chat got two real replies in the transcript. They took about 9 s
  because screen-on-prompt sends an image to E2B.
- Captured on screen with the fixed capture script, beside `02-chat.jpg`.
- `dotnet test`: **397 passed**, including a new `PanelFiles` test. The shell builds with 0
  warnings. `node --test` panels: 10/10. Launcher and dev-server pytest: 9 passed. All
  PowerShell scripts are ASCII.
- **Not verified:** real blur, because Windows transparency is off.

## Found, not fixed

- The QA profile imported the owner's legacy `.local/llama-server.json`, so it shared the owner's
  model port 18771 and used the owner's running model server. Two profiles should not share a
  model port.
- With screen-on-prompt, SORA calls the automatic screenshot "the image you provided".
- The owner's running SoraShell (started before this fix, on 8765) must be quit and started
  again to pick up a working port. It was not touched.

HOW_TO_USE.md: updated (transparency setting, port troubleshooting).
