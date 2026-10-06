# GUI rewrite on WebView2 — plan

Prepared by **Opus 5.5**, 2026-10-06, after the owner's decision: "We are absolutely going with
WebView." Status: **plan; nothing implemented yet.** It serves [VISION.md](../../VISION.md) and
[V1.md](../../V1.md). The approved visual baseline is unchanged: the
[concept images and design v0.1](../gui/reference/README.md).

Agent-activity display is **deferred** by the owner: get the GUI into a good place first.

## Why

The concepts depend on glass panels, glow, rounded translucent windows, smooth motion and a
graph. WinForms has none of these built in. The current Settings window shows the gap: a stock
list, rows of system buttons and debug status text. HTML and CSS do all of this natively, and
LLM contributors write them fluently.

## Architecture

```text
SoraShell.exe (existing C# host)                    SORA Core (unchanged)
  windowless presence, tray, shortcut, single         local HTTP API + events
  instance, managed Core start/Quit, placement
  │
  ├─ one shared WebView2 environment
  │    ├─ Chat window      ┐  borderless Windows 11 windows with a system backdrop;
  │    ├─ Settings window  │  page content is HTML/CSS/JS from clients/panels/
  │    └─ (later panels)   ┘
  │
  ├─ request filter: adds the owner token to Core API calls, so the token never enters JS
  └─ message bridge: window actions, file picker, open another panel, preferences,
     and (later) element positions for SORA's pointing
```

- **The host stays.** Lifecycle, tray, single instance, managed Core, shortcut, panel placement
  and UI preferences are already built and verified. Only the window *contents* change.
- **Pages are served offline** from `clients/panels/` through WebView2's folder-to-virtual-host
  mapping, so a panel still opens when Core or the model is down. That keeps the roadmap's
  model-independent recovery.
- **Data:** pages call Core's existing API with `fetch`, reusing the PWA's `api-client.js` and
  `sync.js` (reconnect and replay). The host injects the `Authorization` header in
  `WebResourceRequested`. There is no new Core API unless a gap is found.
- **Host-only actions** go through a small typed message bridge (`postMessage` in both
  directions): close, hide, minimise, drag, resize, open another panel, pick a file, read or save
  UI preferences. Every message is validated on the C# side, and unknown messages are dropped.
- **Code:** plain HTML, CSS and ES modules, with no framework and no build step. Nothing extra is
  installed on the owner's machine. A framework can be added later if a panel needs one.
- **One design system:** `clients/panels/shared/` holds the colour, spacing, radius and type
  tokens taken from the concepts, plus the shared pieces (window chrome, card, info tile, chip,
  category rail, buttons, inputs, toggles, toasts).

## Honest-data rules (unchanged from the roadmap)

The concepts are visual references, not data contracts. Never show a value Core does not supply:
no invented importance or relevance scores, VRAM figures or run results. An unavailable value is
hidden or labelled unavailable. Chips describe things that actually happened.

## Stages

| Stage | Delivers | Gate (must pass to continue) | V1? |
|---|---|---|---|
| **W0 Spike** | One borderless glass Chat window in the shell. It loads from `clients/panels/`, sends and receives on an isolated Core with the token injected, and has drag, close and hide | Real blur of the desktop behind the panel; screenshot beside `02-chat.jpg` looks right to the owner; text is crisp at 100 % and 150 %; opening takes under about 1 s; typing, IME and Enter/Shift+Enter work | Yes |
| **W1 Foundation** | Design tokens and shared components; typed message bridge; panel loader with offline and "Core unavailable" states; screenshot script for review | Component gallery page reviewed against the concepts; bridge tests (C#) and component tests (`node --test`) pass | Yes |
| **W2 Chat** | Transcript, composer, Stop, attachments, voice button, tool chips (memory searched or opened, motion dispatched, task reported), new-message jump; parity with today's Chat | Everything the current Chat does still works; V1 steps 2–6 can be run from it | Yes |
| **W3 Settings** | Generated from Core's field metadata (category, group, label, type, effect tier). Each category follows the concept's Models pattern: summary card, information tiles, Advanced folded away. Save, Reload model, drafts, conflicts and recovery keep today's semantics | All 129 fields reachable; the brain model can be changed in two clicks; V1 step 8 passes | Yes |
| **W4 Switch over** | The shell opens the web Chat and Settings. The WinForms versions are kept but no longer opened | One week of daily use without falling back | Yes |
| W5 Remaining panels | Voice, Activity, Agents, Project paths, Appearance, then Memory (Overview/Search) | Per panel: parity, then concept styling | After V1 |
| W6 New surfaces | Automations window; Memory graph once real connections exist; spatial language (panels report element positions so SORA can point at them; pulses; anchored notes); agent activity | Per feature | After V1 |

## Verification

- **Look:** a script captures each panel window (the PrintWindow approach already used in QA) and
  saves it beside the matching concept. The owner reviews pairs of screenshots, not code.
- **Behaviour:** `node --test` for page logic, C# tests for the bridge and token injection,
  existing Python API tests for data, and native launches in isolated QA profiles.
- Labels as usual: fixture, component, native, live. A screenshot is not acceptance of behaviour.

## Risks and how the spike settles them

- **Translucency (required).** A transparent WebView2 background over a Windows 11 system
  backdrop (acrylic) is supported, but blur behind web content must be proven on the owner's GPU
  and Windows build in W0. If a route fails, try the next one (system acrylic, composition-based
  blur), not a solid colour.
- **Memory.** All panels share one WebView2 environment (one browser process tree), and hidden
  panels are suspended. The spike measures this.
- **Startup speed.** The environment is created once with the host and pages are preloaded
  hidden, so summoning Chat is instant.
- **The owner's machine.** Windows PowerShell 5.1 and Store Python don't affect WebView2. The
  runtime (154.x) is installed and the NuGet package (1.0.4258.31) resolves.

## Decisions taken in this plan (the owner may change them)

1. Plain HTML/CSS/JS with no framework or build step.
2. The token is injected by the host and never reaches page code.
3. Settings is generated from Core's field metadata, not hand-built per field.
4. The frozen WinForms panels stay in the repo until their web replacements pass their gates.

## Owner decisions (2026-10-06)

- **Font:** not decided yet. The typeface is a single design token (`--font-ui` in
  `clients/panels/shared/`), so changing it is a one-line edit. It starts as Windows' Segoe UI
  Variable.
- **Translucency is real.** Panels show a live blurred view of the desktop behind them, as in the
  concepts ("Apple has proved it works without sacrificing performance with Liquid Glass"). Solid
  dark glass is **not** an accepted design alternative. It may appear only as an automatic
  fallback where Windows itself disables transparency (transparency effects turned off, battery
  saver, or remote sessions), and that is reported, not hidden. W0 must show real blur on the
  owner's machine at good frame rates.
