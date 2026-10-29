# Training the memory manager's layers

Written 2026-10-09 by Opus 5.5. Design: [MEMORY_MANAGER plan](../plans/MEMORY_MANAGER_2026-10-08.md)
§4. Code: `src/sora/memory/training.py`, run by `scripts/memory/train_layers.py`.

Nothing is trained until you run `--train`, and nothing changes what SORA does until you also
pass `--adopt` **and** the new layer beats the rule it replaces on held-out examples.

## What gets trained

Four tiny logistic models, each a few hundred bytes, trained on the CPU in seconds:

| Layer | Question | Rule used until trained |
|---|---|---|
| `acceptance` | Is this moment worth keeping? | Keep everything her brain chose to remember |
| `relevance` | Does her reply (later: a read result, image or clip) belong with your words? | Similarity to your words ≥ 0.79 |
| `same_subject` | Are two memories about the same fact (a repeat or an update)? | Similarity ≥ 0.85 |
| `update` | Given the same subject, does the newer one replace the older? | Words like "now", "anymore", a changed number, or a negation |

They sit on top of EmbeddingGemma 2. Fine-tuning EmbeddingGemma itself is a later, separate step
(plan §4), needed only if reports show these layers have stopped improving.

## Where examples come from

1. **Your actions** (automatic). From now on the memory manager logs every decision with its
   features in `<profile>\memory\decisions\<date>.jsonl` (IDs and numbers only, never memory
   text). Training joins them with what you did later:
   - you deleted a memory: not worth keeping;
   - you corrected a memory: worth keeping, and the correction and the original are an
     update pair;
   - a recalled memory her answer used: worth keeping (recorded once the Memory window marks
     use);
   - never recalled in 90 days: weakly not worth keeping.
2. **Label files** you, an agent or a converted dataset provide, as JSONL in
   `training\memory\labels\` (shared, in the repo) or `<profile>\memory\labels\` (yours only).
   One example per line:

   ```json
   {"layer": "comparison", "a": "My favourite colour is teal.", "b": "My favourite colour is now green.", "label": "updated", "days": 30}
   {"layer": "acceptance", "text": "My mum works night shifts.", "label": 1}
   {"layer": "relevance", "owner": "My exams start on the 14th of May.", "part": "Good luck with revision!", "part_type": "reply", "label": 1}
   ```

   - `comparison` labels are `same`, `updated`, `related` or `unrelated`. They feed both
     `same_subject` and `update`.
   - Optional: `weight` (default 1), `group` (examples sharing it stay on one side of the
     held-out split), `existing` (for acceptance: texts already remembered), `own_thought`.
   - Text is embedded with the same model and features Core uses, so a free dataset of
     sentence pairs (paraphrase, contradiction, update) can be converted line by line.
3. **Labelling her real decisions.** Export the decisions with their memory texts, label them,
   and put the file back:

   ```powershell
   uv run python scripts/memory/train_layers.py --export-unlabelled .local\memory-to-label.jsonl
   ```

   Each line has `memory`, `other` or `part`, what the manager decided, `how_to_label` and
   `"label": null`. Set each label to 1 or 0 (by hand, or ask an agent), then save the file into
   `<profile>\memory\labels\`. The exported texts are your memories: keep the file on this PC.
4. **Fabricated examples** (`training\memory\labels\fabricated\`, made from the probes) are used
   only with `--include-fabricated`, at a third of the weight. They exercise the program; they
   are not you.
5. **Bootstrap examples from public datasets** (from 2026-10-23). The datasets live in
   `training\memory\datasets\` (git-ignored; its `README.md` says what each is for and where to
   download it). Convert them into a labels folder at half an owner label's weight, plus
   LongMemEval test files that are never trained on:

   ```powershell
   uv run --with pyarrow python scripts/memory/convert_datasets.py --out <state>\memory\labels --test-out <state>\memory\tests
   uv run python scripts/memory/evaluate_layers.py --state-root <state> --tests <state>\memory\tests
   ```

   `evaluate_layers.py` scores each layer's newest saved version against its fixed rule on the
   test files. Use an isolated state folder for experiments, not your profile. The first round
   (2026-10-23, [evidence](../verification/MEMORY_LAYERS_BOOTSTRAP_Opus-5.5_2026-10-23.md))
   didn't beat the fixed rules well enough to adopt any layer.

## Steps

```powershell
# 1. See what is available (reads only; SORA can stay running):
uv run python scripts/memory/train_layers.py

# 2. Train when a layer shows "yes" under Trainable. Saves candidates and a report:
uv run python scripts/memory/train_layers.py --train

# 3. Make the better ones active:
uv run python scripts/memory/train_layers.py --train --adopt

# Which version each layer uses, and every saved version:
uv run python scripts/memory/train_layers.py --list

# Go back to an older version:
uv run python scripts/memory/train_layers.py --rollback update update-20261101T120000
```

- A layer needs at least 40 examples with 10 of each answer (`--min`, `--min-per-class`).
- 20% of examples are held out, grouped so paraphrases of one memory never straddle the split.
  The trained layer and the fixed rule are both scored on them. `--adopt` activates the layer
  only if its balanced accuracy is at least 0.02 higher.
- Reports go to `<profile>\memory\layers\reports\<time>.md` (and `.json`), with the held-out
  mistakes. Versions go to `<profile>\memory\layers\<layer>\`, and `active.json` names the one
  in use. With no `active.json`, a layer uses its fixed rule.
- A running SORA uses an adopted layer from the memory manager's next run (the next memory she
  makes); no restart is needed.
- `--state-root` trains another profile (the default is the Desktop shortcut's), and `--cpu`
  embeds on the CPU.

## What a trained layer changes today

The manager uses the active layer for its decisions, its links and the decision log. Removing a
memory (acceptance) or marking one replaced (update) is still only recorded, not applied. Those
take effect once the Memory window lets you review them (plan step 5), because they change
what you told her.
