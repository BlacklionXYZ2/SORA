# W0 web Chat: checks for the owner's machine

Written by **Opus 5.5**, 2026-10-06, for the [WebView2 rewrite plan](../plans/GUI_WEBVIEW_REWRITE_2026-10-06.md).
W0 and W1 were built and tested in a Linux container: page logic, the C# request forwarding and
message checks, a real Core with the deterministic model, and headless Chromium renders. None of
that shows what only Windows can: the blurred desktop behind the panel, text sharpness at your
scaling, speed, and typing in the real window. These checks are the W0 gate. Report what you see;
nothing here needs code.

## Start

```powershell
git pull
.\Start-SORA.ps1 -WebPanels            # quit SORA first if she is running
```

Open Chat (Ctrl+Alt+Space or the tray). The window titled **SORA · Chat** is the new one.

## Checks

| # | Check | Pass when |
|---|---|---|
| 1 | **Real translucency** | The desktop behind the Chat window is visibly *blurred* and tinted, as in `02-chat.jpg`; moving the window over different backgrounds changes what shows through |
| 2 | **Compare routes** | Quit, then `.\Start-SORA.ps1 -WebPanels -PanelBackdrop Accent`. Say which of System (default) or Accent looks closer to the concept, or whether neither works |
| 3 | **Smoothness** | Dragging the window and scrolling the conversation stay smooth (no stutter) on your GPU while SORA's model is loaded |
| 4 | **Look** | `.\scripts\capture-panel.ps1` saves the window beside the concept in `.local\panels-review\`. Does it look right? Note anything that jars: colours, glow, spacing, fonts |
| 5 | **Sharp text** | Text is crisp at your usual scaling and at 150 % (Settings → Display → Scale) |
| 6 | **Opening speed** | The second and later openings of Chat feel instant (under about a second). The first may take longer while WebView2 starts |
| 7 | **Typing** | Enter sends; Shift+Enter makes a new line; the reply arrives; **Stop** (the red button while she answers) stops her |
| 8 | **Window handling** | Drag by the title bar (snapping to screen edges works); resize from the edges; minimise, maximise and close (close only hides it) |
| 9 | **Microphone button** | Opens the existing Voice window |
| 10 | **Core down** | With Core stopped, the panel says Core is not reachable, keeps your draft, and recovers by itself when Core is back |

## If something fails

- **No window or an error box saying the web panel could not start:** note the message. The
  WebView2 runtime comes with Windows 11; the error says what is missing.
- **No blur (solid or black background):** say which route (`System` or `Accent`) and your Windows
  version (Settings → System → About). Check Settings → Personalisation → Colours →
  **Transparency effects** is on. A solid look is what SORA shows deliberately when it is off.
- **Anything else:** describe what you did and what you saw. Screenshots from
  `capture-panel.ps1` help.

Go back to the old Chat at any time by starting without `-WebPanels`.

## Known gaps (planned for W2, not W0 failures)

Attachments, activity and memory chips, the "new messages" anchor and history paging of the old
Chat; voice built into the Chat window; the Settings window (W3).
