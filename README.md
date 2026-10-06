# SORA

SORA is a digital person living on a Windows desktop:
one continuous character with her own personality, presence and capabilities, a local brain,
voice, screen awareness, a 3D body and trusted specialist agents (Cody, Hermes, Aggie and
Claude) for heavy work. Her identity, memory and task state live in Core, not in any model.

**Read [VISION.md](VISION.md) first. It is the top authority.** The current milestone is
[V1](V1.md): a usable product you can talk to, and who talks, moves and indicates back.

## Current state (2026-10-05)

- **Core runtime, phases P00–P15:** largely complete. The work covers durable SQLite state and
  memory, concurrent tasks, Hermes/Codex/Antigravity/local-model providers, owned Git worktrees
  for coding writes, an authenticated local API, Windows UI Automation perception and action,
  the Unity avatar with physics, local voice, the PWA, the widget, the full app and the portable
  release. Open items are listed at the top of the
  [implementation plan](SORA_IMPLEMENTATION_PLAN.md).
- **Active work: V1.** The windowless GUI host (from the owner's
  [concept images](docs/gui/reference/README.md)) becomes the ordinary launch, and the local
  model, voice, screen awareness, movement and agents are joined into one working product. Work
  follows [V1.md](V1.md)'s acceptance test. GUI stage status is in the
  [GUI roadmap](SORA_GUI_IMPLEMENTATION_ROADMAP.md) §4.0. Automations and the memory graph are
  after V1.
- **Verification:** `pytest` 904 passed / 25 opt-in hardware skips, `ruff` clean and
  `mypy --strict` clean (independent rerun 2026-10-05). Component tests are not native GUI,
  live-model or hardware acceptance; the roadmap tracks those gates separately.

## Quick start (Windows PowerShell, `uv` and the .NET SDK installed)

```powershell
.\scripts\bootstrap.ps1          # create the locked Python environment
.\scripts\verify.ps1             # Python tests, lint, strict typing, schema and PWA checks
.\Start-SORA.ps1 -Client Shell   # build, start Core, open the native app (windowless SORA)
```

Plain `.\Start-SORA.ps1` still opens the older, frozen full app; V1 makes the native app the
default.

`Start-SORA.ps1` keeps state in `.local/manual-test`, binds Core to `127.0.0.1` and registers
the specialists installed on this machine. See [local try-out](docs/runbooks/SORA_LOCAL_TRYOUT.md)
for models, voice and the other launcher options.

C# client checks are separate from `verify.ps1`:

```powershell
dotnet test clients/csharp_tests/csharp_tests.csproj
dotnet build clients/desktop_shell/desktop_shell.csproj
```

Headless Core, CLI and per-provider commands (`python -m sora --once …`, `--provider hermes`,
`--provider codex`, `--serve`, remote pairing) are documented phase by phase in the
[previous README](docs/history/README_PHASE_HISTORY_2026-10-03.md) and in
[`docs/runbooks/`](docs/runbooks/).

## Repository layout

| Path | Contents |
|---|---|
| `src/sora/` | Python Core: runtime, API, persistence, providers, routing, workspaces, desktop, voice, vision, embodiment |
| `tests/` | Python test suite. Hardware, native and live-model tests are opt-in skips |
| `contracts/` | Versioned JSON Schemas (`schema/v1`) exported from the Pydantic contracts |
| `clients/desktop_shell/` | **The native app**, SORA's only active client (opt-in launch until V1 makes it the default) |
| `clients/desktop_app/`, `clients/desktop_widget/` | Older full app and compact widget. **Frozen**: kept, not developed |
| `clients/unity/` | Unity 6 avatar/overlay project |
| `clients/windows_*` | Out-of-process Windows helpers: UIA observation, capture, press, type |
| `src/sora/pwa/`, `clients/pwa/` | Browser client (served by Core) and its tests. **Frozen** |
| `clients/csharp_tests/` | C# client tests |
| `identity/` | SORA's persona, values, behaviour, speech style and embodiment |
| `config/` | Example settings and llama.cpp configuration |
| `scripts/`, `packaging/` | Bootstrap, verification, release and install tooling |
| `docs/` | Documentation; start at [docs/README.md](docs/README.md) |
| `changelog/` | One model-attributed record per change; see [changelog/README.md](changelog/README.md) |

Runtime state, credentials, models and QA artefacts (`.local/`, `data/`, `*.db`) are never
committed.

## Documentation

| Read | For |
|---|---|
| [VISION.md](VISION.md) | **Top authority:** who SORA is, how she works, where she is going |
| [V1.md](V1.md) | The current milestone: scope, acceptance test, what is left |
| [SORA_GUI_IMPLEMENTATION_ROADMAP.md](SORA_GUI_IMPLEMENTATION_ROADMAP.md) | GUI stage status (§4.0), stages and acceptance gates |
| [SORA_IMPLEMENTATION_PLAN.md](SORA_IMPLEMENTATION_PLAN.md) | Architecture invariants, contracts, P00–P15 phase checklist and risks |
| [SORA_OVERVIEW.md](SORA_OVERVIEW.md) | The original specification, preserved verbatim |
| [docs/README.md](docs/README.md) | Map of every documentation folder and where history lives |
| [docs/verification/README.md](docs/verification/README.md) | Evidence records and which phases were independently verified |

## Contributing

All contributors, human or model, follow [AGENTS.md](AGENTS.md). In short: never delete files;
write a changelog in your own model name for every change; keep fixture, component, native,
live-model and hardware evidence separate; and don't commit or push unless the owner asks.
