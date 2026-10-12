# Decision layer stage 1: native Laya (Q8_0 GGUF on the GPU) chooses tool families; shadow by default

Model name: **Opus 5.5**. Checkpoint **2026-10-08 20:01:00 +01:00**, Europe/London. Status:
**implemented, component-tested, measured live with the real model on the owner's GPU.** The
owner has not yet run it inside a launched SORA. The owner asked: "start on the decision layer
implementation … This will be the first stage that will require more models to be downloaded."

Owner answers:
- **Laya is a specific released model.** It is Convai Innovations' Laya, and the owner pointed
  to the Q8_0 GGUF at mys/laya-GGUF.
- **"Just native laya for now, it will be trained later."**
- **Scope:** tool families per turn.
- **GPU:** the owner has ROCm PyTorch. That GGUF needs ggmlc's runner instead, which ships
  Vulkan (used here) and CUDA builds, not ROCm.

## Changes

- New package `src/sora/decision/`:
  - `families.py`: seven families mapped to companion operations (with dependencies), plus Laya
    questions asked as neutral A/B choices. The delegate question names the owner's agents.
  - `laya.py`: a daemon client with lazy start and restart, a 2 s timeout and fail-open.
  - `gate.py`: follows Settings and is only enabled by owner launches.
  - `settings.py`: mode `off`/`shadow`/`enforce` (default shadow), threshold 0.25, device, and
    runner and model paths.
- `read_turn.collect_reads(allowed=…)` narrows the brain's operations. `SoraRuntime` asks the gate
  before each companion turn and records a `decision.families` trace that shares its correlation
  ID with `companion.read_turn`.
- `--listen-on-start` (owner launches) also warms the decision layer, and Core shutdown closes the
  runner. The runner exiting on end of input was confirmed live.
- `AppSettings.decision` was added, and older files load with the defaults. Settings → Models →
  Decision layer (Laya), with device and paths under Advanced. The schema was exported, and the
  panel fixture now has 140 fields.
- `scripts/setup-decision-layer.ps1` downloads, with SHA-256 checks, to `.local/decision/`:
  - the ggmlc v0.9.7 `laya` runner, Vulkan build
    (`e879d1e9…0ae6`);
  - `laya_english_q8_0.gguf` (`6243305f…8382`).
- New plan [DECISION_LAYER_2026-10-08](../docs/plans/DECISION_LAYER_2026-10-08.md); HOW_TO_USE
  setup step 5; `docs/README.md`.

## Verification

- **Fixture/component:**
  - pytest: 1076 passed, 25 skipped, 4 xfailed, plus 365 passed in decision and runtime after the
    last edit.
  - ruff and mypy (326 files) pass, `export-contracts --check` passes, compileall passes, and the
    panel tests give 33 passed.
  - New tests are in `tests/decision/test_decision_layer.py` (10): families and dependencies;
    question shape; default paths; the daemon protocol and threshold with a stand-in daemon;
    failing open and restart; only enforce narrows; the brain offered only chosen families; agent
    names; and the gate off unless enabled.
  - `.\scripts\verify.ps1` itself could not run. `uv run` tries to reinstall SORA into `.venv`,
    whose `sora.exe` the owner's running SORA holds, so each step was run with `uv run --no-sync`
    (the PWA step was not run).
- **Live, real model:** 24 SORA-style messages with my own labels.
  - Laya via torch on the CPU: about 1.5 s per message; recall 0.65 at 0.5.
  - The Q8_0 GGUF on Vulkan (RX 9070 XT) through SORA's client: warm start 0.9–1.0 s; median
    20–25 ms and max about 160 ms per message. At 0.25: **0/24 messages missing a needed family**
    (1/24, "Ask Pip…", before agent names were added), with 3.4 of 7 families offered on average.
- **Not run:**
  - a launched SORA with the gate on: the owner's SORA is running older code and was not
    restarted;
  - enforce mode on real conversations;
  - an end-to-end runtime test of the trace (component tests cover the gate, the narrowing and
    the client separately).

## Leftovers from the first attempt (not deleted)

Before the owner pointed to the GGUF, I installed the torch route. Nothing uses these now; the
owner may delete them:

- `.local/decision-runtime/`: the CPU torch environment, about 1 GB.
- `.local/decision-runtime.incomplete-20261008/`: a failed first creation.
- `.local/decision-runtime-rocm/`: a small venv over the owner's system ROCm torch.
- `.local/models/laya/`: the full `convaiinnovations/laya` repository, about 2.2 GB, with three
  checkpoints.

`pyproject.toml` and `uv.lock` were returned to their earlier content.

HOW_TO_USE.md: updated.
