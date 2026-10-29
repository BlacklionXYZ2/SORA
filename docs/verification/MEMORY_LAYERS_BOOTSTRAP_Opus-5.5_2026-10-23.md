# Memory layers: first training round on public-dataset bootstrap labels

Model name: **Opus 5.5**. Date: **2026-10-23**. Code: `scripts/memory/convert_datasets.py`,
`scripts/memory/evaluate_layers.py`, `training/memory/labels/written/update_pairs.jsonl`; the
existing `scripts/memory/train_layers.py`. Plan:
[MEMORY_MANAGER](../plans/MEMORY_MANAGER_2026-10-08.md) §4. Datasets:
`training/memory/datasets/README.md`.

**Kind of evidence: component (offline training and scoring).** Embeddings came from EmbeddingGemma
2 (Q4_K_XL, GPU) through Core's own embedder class and features. The state folder was
`.local/memory-bootstrap-qa-2026-10-23`. The owner's profile was only read (its database,
read-only), and no layer was activated anywhere. None of the data is the owner's.

## Labels

All training rows are weighted 0.5 (half an owner label) and grouped so related rows stay on one
side of the held-out split.

| File | Rows | Layer(s) |
|---|---|---|
| Dialogue NLI, verified set, unanimous pairs only | 700 same, 700 updated, 700 unrelated | same_subject, update |
| Written update pairs (Opus 5.5) | 42 same, 38 updated | same_subject, update |
| PAWS paraphrases | 300 same | same_subject, update |
| Multi-Session Chat persona summaries | 750 keep, 750 don't | acceptance |
| Synthetic-Persona-Chat | 750 real replies, 750 replies from other conversations | relevance |
| **Test only:** LongMemEval | 68 real update pairs plus 68 unrelated pairs; 300 evidence turns plus 300 task-only turns | same_subject, update, acceptance |

**Changed from the proposal, after inspecting the data:**
- **Dialogue NLI:** its training split's automatic labels were noisy, so the verified set is used
  instead, with the pairs all three annotators agreed on.
- **PAWS:** its non-paraphrases are usually the same subject with a detail changed, which isn't
  "different subject", so only its paraphrases are used.

## Results

Balanced accuracy, where 0.5 is chance.

| Layer | Held-out split: trained | Held-out split: fixed rule | LongMemEval: trained | LongMemEval: fixed rule |
|---|---|---|---|---|
| acceptance | 0.736 | 0.500 | 0.63 (keeps 99%; rejects only 27% of task-only turns) | 0.50 (keeps everything) |
| relevance | 0.745 | **0.761** | no test set | no test set |
| same_subject | 0.915 | 0.836 | 0.89 | **0.919** |
| update | 0.763 | 0.516 | recall 0.941 (no repeats in the test, so recall only) | recall 0.868 |

## Reading

- **No layer is ready to adopt.**
  - `same_subject` beats its rule on the datasets' own held-out split but loses on real long chat
    turns. It calls 21% of unrelated pairs the same subject; the rule calls 1.5%. Short persona
    sentences have a different similarity range from long messages.
  - `relevance` loses to its rule even on its own data. The negatives (a reply from another
    conversation) are too easy to be informative, and the positives are often generic ("Me too!").
  - `acceptance` is better than "keep everything", but on long first-person messages it still keeps
    nearly everything.
  - `update` looks better than its cue-word rule, but this test has no repeats, so a layer that
    always says "updated" would score 1.0.
- What this round shows is that the pipeline works end to end on about 6,500 labelled rows. The
  bootstrap data teaches the layers the datasets' style rather than the owner's.

## Not run

- Adoption into any profile.
- A relevance test set.
- Repeat (non-update) pairs in the update test.
- Any of the owner's own labels: there are none yet (4 memories, 8 logged decisions).
