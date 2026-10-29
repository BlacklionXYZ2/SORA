# The Motion window: choosing her motion model (settings, catalogue and panel)

Model name: **Opus 5.5**. Checkpoint **2026-10-27 02:15 UTC**. Status: **implemented and verified
(component and fixture); the choice is saved but not yet acted on by her player**.

The owner asked to "build the motion model settings now" and set up the pipeline for ARDY. They
sent a draft GUI (ChatGPT) and said the vocabulary should use our keywords. This change builds
the settings and the window. The motion service that actually drives her comes next.

## Changes

- **`motion` settings section** (`src/sora/embodiment/motion_settings.py`, in `AppSettings`):
  - `engine` (algorithmic, the default; ardy; custom);
  - `ardy_precision` (fp16/fp32), `ardy_steps` (2 to 10, default 4);
  - `custom_version`, `custom_size`, `lab_path` (blank: `motion-lab` beside SORA).
  - All apply at the next start (`BOOT_FIELDS`), under a new **Motion** settings category (11
    categories, 151 fields). Settings saved earlier load with the defaults.
- **Catalogue** (`src/sora/embodiment/motion_catalog.py`, public contract `motion-catalog`,
  schema exported):
  - Core reads motion-lab's `catalog/catalog.json`, validates it, puts the always-available
    algorithmic engine first, and marks a model `missing` when a file it names has gone.
  - A missing or unreadable catalogue leaves only the algorithmic engine, with a note.
- **Routes** (`src/sora/api/motion_routes.py`; `routes.py` only dispatches):
  - `GET /api/v1/motion/catalog`;
  - `GET /api/v1/motion/preview?name=previews/<file>.json`;
  - both owner-local, read-only, bounded in size, with names restricted to the catalogue's
    previews folder.
- **Motion panel** (`clients/panels/motion/`), after the owner's draft. Three changes from it:
  - the algorithmic system is a third source;
  - the measurements are real (beside real motion capture), not invented scores;
  - the preview is a stick figure playing motion the model actually generated, not renders.
  - **What it has:**
    - source cards;
    - ARDY precision and step pills;
    - custom version and size pills, with planned sizes greyed out;
    - a details block and the measurements;
    - the save bar (saves only the changed `motion.*` keys with the revision read).
  - **Banners** say when a saved choice waits for a restart, and that ARDY and custom models
    aren't connected to her player yet.
- **Wiring:**
  - `shared/api.js`: `motionCatalog`, `motionPreview`;
  - `shared/bridge.js` and `PanelBridge.cs`: `motion` is openable;
  - five new icons;
  - the Settings panel's Motion category has a "Choose her motion model…" button.
  - **Desktop shell:** the web page size, the tray menu ("Motion / her motion model"), the
    command menu, the classic Settings links, and the panel allow-lists in `ShellInstance`,
    `ShellPreferences` and `ShellProfile`.
- **HOW_TO_USE.md:** a Motion entry under The glass windows; "Last updated" line.
- **Tests:**
  - `tests/embodiment/test_motion_catalog.py` (9);
  - `clients/panels/tests/motion.test.mjs` (7);
  - `tests/runtime/test_app_settings.py`'s pinned counts updated (145 → 151 fields, 10 → 11
    categories), with the Motion fields pinned.

## Verification

- **`scripts/verify.ps1`** (fixture and component): ruff clean, strict mypy (365 files),
  contract schemas current, 1,154 passed / 26 skipped / 4 xfailed, panel tests 147 passed.
- **`dotnet build`** of the desktop shell: 0 warnings. **`dotnet test`:** 420 passed.
- **The panel rendered against real data** (headless Edge, a scratch server answering the three
  calls from a temporary settings controller and motion-lab's real catalogue). Screenshots and
  the server are in `.local/motion-panel-qa-2026-10-27/`. Two bugs found and fixed that way:
  banner text misaligned, and no empty-state message for the algorithmic preview.
- **Not run:**
  - the panel inside SoraShell (WebView2);
  - a real Core serving the routes over HTTP (the route handler is tested directly);
  - the owner's own SORA (untouched).

## Limits and next

- **The engine choice has no effect on her yet:** her player always uses the algorithmic system.
- **Next:** the motion service (ARDY driven by the keyword phrase table and a target velocity),
  then Unity applying its poses.

HOW_TO_USE.md: updated. Nothing committed.
