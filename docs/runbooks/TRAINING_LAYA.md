# Training Laya, SORA's decision layer: a learning guide

Written **2026-10-08**, Opus 5.5, for the owner. It explains the ideas first, then the exact steps.
The design is in [DECISION_LAYER_2026-10-08](../plans/DECISION_LAYER_2026-10-08.md).

**Where things stand:** SORA runs **native (untrained) Laya** in **shadow** mode. It decides every
message and logs the decision, but takes no tools away. The training pipeline below works end to
end and was checked with a tiny smoke run, but no real training has been done yet, because the
real data (your own messages) is only now being collected. Don't train until you have it.

---

## Part 1: The ideas

### What Laya is

Most models you hear about, Gemma included, are **generative decoders**: they read text and
predict the next token, again and again. Laya is a different kind of model, an **encoder with a
decision head**:

- **The encoder** is ModernBERT-large, with 395M parameters. It reads the whole input at once,
  in both directions, and turns every token into a vector: a list of numbers that captures
  meaning in context. It never generates anything.
- **The decision head** is small: a few million parameters on top. It looks at the vectors at
  special `[MASK]` positions, one per answer option, and turns them into a score for each
  option.
- **Softmax** turns the scores into probabilities that add up to 1.
- **Temperature calibration** then divides the scores by a fitted number, T, before the softmax,
  so that "0.8" really means right about 80% of the time.

Laya sees this input, as `laya info` shows:

```
[CLS] choice question: Does answering this message need <family description>? [SEP]
      [MASK] A: yes, it needs that  [MASK] B: no, it does not [SEP] <the owner's message> [SEP]
```

One forward pass answers every question for a message (SORA asks one per tool family), in about
20 ms on your GPU.

### What "training" changes

**Fine-tuning** means continuing to train a model that has already been trained, on your own
examples:

1. Show it a message and a question, and the correct answer (A or B).
2. It predicts probabilities. The **loss** measures how wrong it was. SORA uses `soft-ce`
   (cross-entropy): −log(probability given to the right answer). That is 0 when it is certain and
   right, and large when it is confident and wrong.
3. **Backpropagation** computes, for every weight, which direction would lower the loss
   (the *gradient*).
4. The **optimiser** (AdamW) nudges every weight a small step that way. The step size is the
   **learning rate** (`--encoder-lr`, `--head-lr`). The head can learn faster than the
   pre-trained encoder, so it gets a higher rate.
5. Repeat over the whole dataset; one pass over it is an **epoch**.
   - **Micro-batch:** how many examples are processed at once (limited by GPU memory).
   - **Gradient accumulation:** how many micro-batches are added together before one step.
     Their product is the effective batch size.

Two choices you will see:

- **Full fine-tune:** all 421M weights train. This is the most capable option, needs a GPU and a
  few GB of memory, and needs hundreds to thousands of examples.
- **`--freeze-encoder`:** only the head trains. This is fast and cheap, but it can only reuse
  what the encoder already understands. Useful for smoke tests and very small datasets.

### LoRA and axolotl: why they are not used here

**LoRA** (low-rank adaptation) freezes the big weight matrices and learns small "adapter"
matrices beside them. That makes fine-tuning *large generative* models (7B and up) feasible on
one GPU. **Axolotl** is a popular tool for exactly that: LoRA or full post-training of generative
LLMs from a config file.

Laya is 421M parameters, so a full fine-tune already fits on your card. It also uses its own
model class and loss, which axolotl does not know. So SORA uses Laya's own trainer
(`laya.train.finetune`). Axolotl would become relevant if you later post-train SORA's *brain*
(Gemma) itself, for example a LoRA on her persona or her tool calling, which VISION.md lists as
a long-term goal.

### Generalisation: why training is "general", not "SORA's 7 families"

You want an extension or plugin to be able to add tools, or whole new families, and have Laya
pick them up without retraining. So Laya is trained on the *skill* "does this message need
*\<description\>*?", not on memorising seven names. To make that work:

- **A catalogue:** families come from `src/sora/decision/families.py` (SORA's 7) plus
  `training/decision/extension_families.json` (media, browser, timers and so on: stand-ins for
  future plugins).
- **Random sampling:** each training row asks about the message's own families plus five others
  chosen at random (`--negatives`). Each message is repeated with different samples
  (`--repeats`).
- **Swapped letters:** the yes/no letters are randomly swapped, so the model has to read the
  option text instead of learning "A means yes".
- **Held-out families:** two families, **calendar** and **smart_home**, are *never* trained on.
  `seed_eval_unseen.jsonl` tests them. That is your measure of "a brand-new plugin family
  works". If it gets worse after training, the model has started memorising instead of reading.

### Data, splits and overfitting

- **Training set:** what the model learns from.
- **Calibration set:** about 10%, set aside automatically to fit the temperatures.
- **Evaluation set:** messages the model never trained on, so its scores tell you how it will do
  on new messages.

**Overfitting** is a model that memorises its training set and gets worse on everything else.
Small datasets overfit fast; the smoke run below shows it. Always compare **before and after on
evaluation sets**, never on training data.

### Reading the evaluation numbers

For each message SORA offers every family whose P(yes) is at least the **threshold**.

- **recall:** of the families a message needed, the share that were offered. A missing family
  means she can't do what you asked. **This matters most.**
- **precision:** of the families offered, the share that were needed. Extras just give her brain
  more to choose from.
- **complete:** messages where *every* needed family was offered.
- **offered:** the average number of families shown, out of the number asked about. Lower is a
  simpler choice for her brain.

Lowering the threshold raises recall and lowers precision. Pick the highest threshold that keeps
"complete" at or near 100%.

### Where labels come from, and how much to trust them

| Source | How it's made | Trust |
|---|---|---|
| `owner` | You wrote or checked it | Best |
| `trace` | Exported from shadow mode: the tools her brain actually used for that message | Noisy: the brain can skip a tool it needed or use one it didn't |
| `seed` | Hand-written starter examples (`training/decision/`) | OK for a start, but not your phrasing |

Real improvement comes from **your** messages. Start by fixing trace labels and marking them
`owner`.

---

## Part 2: The steps

The commands are for PowerShell in the SORA folder. SORA itself can keep running, except while
you train, which needs GPU memory.

### 0. One-time setup

```powershell
.\scripts\setup-decision-layer.ps1          # the runner + Laya Q8_0 GGUF SORA uses (done)
.\scripts\decision\setup-training.ps1       # training environment over your ROCm torch (done)
```

`setup-training.ps1` creates `.local\decision\train-env` on top of your system Python's ROCm
torch, installs `laya` and ggmlc, fetches ggmlc's Laya compiler, and downloads the full-precision
checkpoint if needed. It checks that torch sees your GPU.

### 1. Collect data (shadow mode, days to weeks)

Use SORA normally with Settings → Models → Decision layer → **shadow**. Then:

```powershell
uv run python scripts\decision\export_traces.py
```

This writes `.local\decision\data\traces-<time>.jsonl`, which is git-ignored because it holds your
messages. Each row looks like:

```json
{"message": "pause spotify", "families": ["media"], "source": "trace", "_context": {...}}
```

It also says how many turns Laya at 0.25 would have hidden a tool the brain used. **Review the
file:**
- fix wrong `families`;
- set `"source": "owner"` on rows you checked;
- delete rows you don't want learned.

`_context` shows what Laya scored and the brain chose, to help you review; training ignores it.

**How much data:** aim for a few hundred reviewed rows before the first real run, with every
family and plain chat represented.

### 2. Measure the current model first

```powershell
uv run python scripts\decision\evaluate.py training\decision\seed_eval.jsonl
uv run python scripts\decision\evaluate.py training\decision\seed_eval_unseen.jsonl
uv run python scripts\decision\evaluate.py .local\decision\data\my_eval.jsonl
```

Keep some of *your* reviewed rows aside as `my_eval.jsonl`, never training on them. Note the
results. Native Laya on 2026-10-08:

| Set | Messages | at 0.25: complete / recall / offered |
|---|---|---|
| `seed_eval` (SORA plus extension families, 13 asked) | 35 | 32/35, 0.89, 4.4 |
| `seed_eval_unseen` (held-out calendar, smart_home; 9 asked) | 15 | 14/15, 0.93, 2.7 |

### 3. Train

Stop SORA first, or at least unload its model, to free GPU memory. Then:

```powershell
.local\decision\train-env\Scripts\python.exe scripts\decision\train.py `
    training\decision\seed_train.jsonl .local\decision\data\reviewed.jsonl --name first-real
```

The run's folder `.local\decision\runs\first-real\` gets:
- the expanded training rows;
- the checkpoint;
- `summary.json`;
- Laya's own before/after report, printed at the end (accuracy, loss, ECE = calibration error;
  lower is better).

Useful options:

| Option | Default | What it does |
|---|---|---|
| `--epochs` | 4 | Passes over the data. More can overfit small data |
| `--negatives` | 5 | Other families asked per message (general training) |
| `--repeats` | 3 | Copies of each message with different families sampled |
| `--micro-batch` / `--grad-accum` | 4 / 4 | Effective batch of 16. Lower micro-batch if you run out of GPU memory |
| `--encoder-lr` / `--head-lr` | 2e-5 / 1e-4 | Step sizes. Too high forgets what it knew; too low learns nothing |
| `--freeze-encoder` | off | Train only the head |

### 4. Compile to the GGUF SORA runs

```powershell
.local\decision\train-env\Scripts\python.exe scripts\decision\compile.py --run first-real
```

This produces `.local\decision\runs\first-real\laya_sora_q8_0.gguf`, about 450 MB.

### 5. Compare, then switch, or not

```powershell
uv run python scripts\decision\evaluate.py training\decision\seed_eval_unseen.jsonl `
    --model .local\decision\runs\first-real\laya_sora_q8_0.gguf
```

Run the same three evaluations as step 2. Adopt the new model only if:
- **"complete" did not drop** on any set, the held-out families especially;
- **it improved** on your own `my_eval`.

To switch: Settings → Models → Decision layer → Advanced → **Laya model GGUF** → that file. Then
try **enforce**. The original stays in `.local\decision\`, so going back is just clearing that
setting.

---

## The smoke run, and what it taught

On 2026-10-08 the pipeline was proven end to end. The run used only the head (`--freeze-encoder`),
1 epoch, and 30 seed messages:
1. Training ran on your RX 9070 XT through ROCm.
2. It compiled to Q8_0.
3. SORA's runner loaded the result.

The model got **worse**: 29/35 complete on `seed_eval`, against 32/35 untrained, and its
probabilities became overconfident (thresholds stopped mattering). That is the expected result
of training on far too little data. It is kept in `.local\decision\runs\smoke-20261008\` as an
example, not for use.

## Files

| Path | What |
|---|---|
| `src/sora/decision/` | Families, the runner client, the gate (Core) and the dataset format |
| `training/decision/` | Seed data and the extension-family catalogue (in git) |
| `scripts/decision/` | `setup-training.ps1`, `export_traces.py`, `evaluate.py`, `train.py`, `compile.py` |
| `.local/decision/` | The runner, models, your data, runs and reports (not in git) |
