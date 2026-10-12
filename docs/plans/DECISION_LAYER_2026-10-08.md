# Decision layer (System-1): Laya chooses which tool families the brain sees

Prepared **2026-10-08**, Opus 5.5. Status: **stage 1 implemented (native, untrained Laya; shadow by
default)**. See the [changelog](../../changelog/2026-10-08T200100+0100_DECISION-LAYER-STAGE1_Opus-5.5.md).
Source of the idea: [VISION.md](../../VISION.md), "Decision layer (System-1)": a small fine-tuned
model, Laya-class at about 400M parameters, picks which tools to present. Fewer choices make a
small brain's tool calls reliable, so each tool can have more depth.

## Owner decisions (2026-10-08)

- The model is **Laya** (Convai Innovations, Apache 2.0): a 421M-parameter ModernBERT-large
  decision model that answers typed questions (choice / score / yes-no) with calibrated
  probabilities in one encoder pass.
- **Native Laya for now; it will be trained later.**
- **This stage decides tool families per message.** The separate motion, screen-view and memory
  choosers stay as they are.
- **Runtime:** the owner's Q8_0 GGUF, [mys/laya-GGUF](https://huggingface.co/mys/laya-GGUF)
  (`laya_english_q8_0.gguf`, 451,505,440 bytes). It is compiled by
  [ggmlc](https://github.com/monatis/ggmlc) and is **not** a llama.cpp model. It runs in ggmlc's
  `laya` runner on the GPU. The owner's GPU is AMD, so that means the Vulkan build: ggmlc ships
  Vulkan and CUDA builds but no ROCm one.

## How it works

1. **Families** (`src/sora/decision/families.py`). Each groups companion operations, and some
   depend on others' operations:

   | Family | Operations |
   |---|---|
   | windows | `list_windows`, `inspect_window` |
   | files | `list_files`, `search_files`, `read_file` |
   | memory | `find_memory`, `present_memory` |
   | motion | `pose`, `move`, plus `list_windows` (to walk to a window) |
   | indicate | `look`, `point`, plus `list_windows` and `inspect_window` |
   | delegate | `list_agents`, `delegate` |
   | view_window | `view_window`, plus `list_windows` |

   `finish` is always offered.
2. **Questions:** one per family: "Does answering this message need <description>?". Each is
   asked as a two-option `choice` (A = yes, B = no). Laya's own `noul` type can follow its option
   labels instead of the text on the English checkpoint (upstream issue #156). The delegate
   question names the owner's agents, nicknames included.
3. **Runner** (`src/sora/decision/laya.py`): `laya.exe daemon <gguf> --device <auto|vulkan|cpu>`.
   It reads one JSON line in and writes one JSON line out, after a `{"status":"ready"}` line.
   - It is started lazily, or warmed at owner launches.
   - It is restarted after any failure.
   - It **fails open**: no decision means every tool is offered.
4. **Modes** (Settings → Models → Decision layer):
   - **shadow** (default): Laya decides and the decision is traced, but every tool stays offered;
   - **enforce:** the brain's operations are narrowed to the chosen families;
   - **off.**

   A family is chosen at P(yes) ≥ **threshold**, which defaults to 0.25.
5. **Traces for training:** `decision.families` records the mode, threshold, model, the families
   and per-family probabilities, and the latency. It shares the turn's correlation ID with
   `companion.read_turn`, which records what the brain was offered and chose. Joined, they are
   labelled training data.
6. **Owner launches only:** the gate is off until Core's `--listen-on-start`, which every owner
   launch passes, enables it. Tests and embedded runtimes never start the runner.

## Measurements (2026-10-08)

24 SORA-style messages with hand-written expected families, run through native Laya:

| Setup | Time per message (7 questions) | Result |
|---|---|---|
| torch on the CPU (laya 0.4.1 package) | ~1.5 s | recall 0.65, precision 0.56 at 0.5 |
| Q8_0 GGUF, Vulkan, RX 9070 XT, through SORA's client | median 20–25 ms, max ~160 ms | at 0.25: **0/24 messages missing a needed family**, 3.4 of 7 families offered on average |

Single-question framing (one 8-way choice) was worse: 8/24 right at the top choice.

These are a small set with labels written by me, not a benchmark. Enforce is therefore opt-in
until real traces confirm the threshold.

## Install

`.\scripts\setup-decision-layer.ps1` downloads, with SHA-256 checks:

- the Vulkan `laya` runner, ggmlc v0.9.7, 17.5 MB;
- the Q8_0 GGUF, about 430 MB.

Both go to `.local/decision/`. `-Build cuda-sm86|cuda-sm89` is for NVIDIA cards.

## Next stages

1. **Owner check:** run in shadow, then switch to enforce and compare replies.
   **Training pipeline ready (2026-10-08):** export, evaluate, train, compile, with general
   (description-based) training and held-out families; see
   [TRAINING_LAYA](../runbooks/TRAINING_LAYA.md). No real training yet: collect shadow traces first.
2. **Calibrate:** fit the threshold per family from real traces (the "decision.families" and
   "companion.read_turn" pairs) and owner corrections.
3. **Fine-tune Laya** on SORA's families. Laya's authors report base 0.36 → fine-tuned 0.77 on
   their typed-decision benchmark. Recompile to GGUF with ggmlc.
4. **Integration families:** manifests' `family`/`examples` from
   [INTEGRATIONS_CLI_DESIGN](INTEGRATIONS_CLI_DESIGN_2026-10-05.md) become families and training
   data; `sora tools preview` shows Laya's choice.
5. **Absorb the separate choosers** (motion keyword, screen view, remember?) behind the same
   interface, removing extra brain calls per turn.
6. **Addressee classifier** for always-on listening
   ([plan](ALWAYS_ON_LISTENING_2026-10-08.md) step 7) as another Laya question.
