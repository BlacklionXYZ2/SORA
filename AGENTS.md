# Contributor guide for SORA

This applies to every contributor, human or model: Codex, Claude, Gemini, DeepSeek, Hermes and
others. The owner runs several models on this repository; these rules keep their work
trustworthy and the documents maintainable.

## Orient before changing anything

1. [VISION.md](VISION.md) is the top authority. Where any plan conflicts with it, the vision wins
   and you raise the conflict with the owner.
2. [V1.md](V1.md) is the current milestone. Work toward its acceptance test, and say which test
   step a change moves forward. Work that moves none of them waits until after V1.
3. [README.md](README.md) gives the current state and layout;
   [SORA_GUI_IMPLEMENTATION_ROADMAP.md](SORA_GUI_IMPLEMENTATION_ROADMAP.md) §4.0 gives GUI stage
   status, and §12 holds the stage you are working on.
4. [SORA_IMPLEMENTATION_PLAN.md](SORA_IMPLEMENTATION_PLAN.md) §2 holds the architecture
   invariants: Core owns state and models are replaceable. Access is set once in Settings; SORA
   asks before changing the owner's files, settings or apps, and action outcomes are verified.
5. [docs/verification/README.md](docs/verification/README.md) shows which earlier work has been
   independently verified.
6. Inspect the current source and run the tests yourself before claiming anything about it.

## Hard rules

- **Never delete files.** That includes plans, snapshots, evidence and changelogs. Superseded
  material moves to a history location with every link updated (see [docs/README.md](docs/README.md)).
- **Write a changelog in your own model name for every change**, following
  [changelog/README.md](changelog/README.md). Never edit or rename another contributor's
  changelog or verification record.
- **Don't commit, push, merge or publish** unless the owner asks in the current session.
- **Leave the owner's running SORA alone.** Don't restart, migrate or reconfigure it, and don't
  touch their data or settings. Use isolated QA state under `.local/<topic>-qa-<date>/`.
- **Report evidence honestly and keep its kinds separate**: fixture, component, native, live model,
  provider, hardware. A green suite, a successful build or a model's own report is not
  acceptance. Say what you did not run.
- **Don't trust Gemini 3.8 Flash's claims on their own.** Before building on a phase it
  implemented (P03A, P06), check the [ledger](docs/verification/README.md#independent-verification-ledger)
  and verify the behaviour you depend on.
- Don't renumber phase/stage IDs, don't tick a box or add a completion timestamp until its gate
  passes, and preserve existing attribution.

## Keeping documents maintainable

- Living documents state the current position **once**. Update the roadmap's §4.0 row and §12
  task line in place.
- Put dated narrative in a log, never in a new "historical handoff" section: roadmap checkpoints
  go to [docs/gui/ROADMAP_CHECKPOINTS.md](docs/gui/ROADMAP_CHECKPOINTS.md) (§4.34 onward),
  roadmap revisions to [docs/gui/ROADMAP_REVISION_HISTORY.md](docs/gui/ROADMAP_REVISION_HISTORY.md),
  and plan progress to [docs/history/IMPLEMENTATION_PLAN_PROGRESS_LOG.md](docs/history/IMPLEMENTATION_PLAN_PROGRESS_LOG.md).
- Evidence goes in `docs/verification/<ID>_<TOPIC>_<model>_<date>.md`; contracts for GUI stages
  in `docs/gui/`.
- Keep sentences readable. Write "904 passed / 25 skipped at 13:47:07", not run-together
  shorthand such as "904Python/25skipped observed13:47:07".

## Verify

```powershell
.\scripts\verify.ps1                                   # ruff, strict mypy, schema export check, pytest, compileall, PWA
dotnet test clients/csharp_tests/csharp_tests.csproj   # C# client tests
dotnet build clients/desktop_shell/desktop_shell.csproj
uv run --locked python scripts/export-contracts.py     # after changing a public contract
```

Hardware, native and live-model tests are opt-in skips. Run them only for a relevant change or
an open gate, and only in an isolated profile.

## Code conventions

- Python 3.12, Pydantic v2 strict contracts (`src/sora/contracts/`), `mypy --strict`, ruff
  (line length 100). Match the style of the surrounding code.
- Public contracts are versioned JSON Schemas in `contracts/schema/v1/`; export them and keep the
  freshness check green.
- `src/sora/runtime/service.py` (about 7,600 lines) and `src/sora/api/routes.py` (about 2,800)
  are already too large. Put new behaviour in a focused module and call it from there, rather
  than adding more methods to `SoraRuntime`.
