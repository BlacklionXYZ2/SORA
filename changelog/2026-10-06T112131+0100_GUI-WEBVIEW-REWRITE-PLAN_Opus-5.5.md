# Plan: rebuild the GUI's windows on WebView2

Model name: **Opus 5.5**. Checkpoint **2026-10-06 11:21:31 +0100**, Europe/London. Status: **plan only**; no code
changed.

## Changes

- New `docs/plans/GUI_WEBVIEW_REWRITE_2026-10-06.md`, written after the owner's decision to use
  WebView2. It covers:
  - the architecture: keep the C# host, use web pages for window contents, inject the token in
    the host, and add a typed message bridge;
  - honest-data rules;
  - stages W0–W6 with gates. W0–W4 (spike, foundation, Chat, Settings, switch-over) are V1;
  - verification, risks, and open questions (font, translucency).
- The roadmap and `V1.md` now point to the plan. The roadmap's GUI-0b WinForms framework choice
  is marked superseded.

## Owner decisions recorded

- The font stays a single design token (`--font-ui`), not decided yet.
- Translucency must be real blur. Solid glass is only Windows' own automatic fallback, and it is
  reported when used. This is added to the W0 gate.

## Verification

- On the owner's machine: WebView2 runtime 154.x is installed, and NuGet resolves
  `Microsoft.Web.WebView2` 1.0.4258.31 (checked in a scratch project).
- The existing PWA client code (`api-client.js`, `sync.js`) was reviewed for reuse.
- Relative links: checked.

## Limits and next

The next step is the W0 spike, which is the go/no-go gate.

HOW_TO_USE.md: no change to usage.
