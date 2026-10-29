# Public datasets for the memory layers

Downloaded **2026-10-23** by Opus 5.5 at the owner's request, to bootstrap the memory manager's
four layers ([runbook](../../../docs/runbooks/TRAINING_MEMORY_LAYERS.md)). Only this note is kept
in git. The data files are ignored (`.gitignore`), because they are large, are licensed
separately, and aren't part of SORA. To get them back, download them again from the sources below.

None of this is the owner's data. Examples converted from these datasets are "bootstrap" labels:
weighted below the owner's own labels, and replaced as real ones accumulate. Converted label
files from datasets with no stated licence stay in the profile's private labels folder.

| Dataset | Used for | Files here | Source | Licence |
|---|---|---|---|---|
| **PAWS** (Wiki, labelled final) | `same_subject`: pairs with nearly identical words but a different meaning (49,401 train, 8,000 dev, 8,000 test; label 1 = same meaning) | `paws_*.parquet`, `paws_LICENSE.txt` | [Hugging Face, google-research-datasets/paws](https://huggingface.co/datasets/google-research-datasets/paws) (Google's own copy; the Cloud Storage links in [the repository](https://github.com/google-research-datasets/paws) returned 403) | Google: "may be freely used for any purpose"; acknowledgement appreciated |
| **Dialogue NLI** | `update` (contradictions between two facts about the same subject) and `same_subject` (entailment as same fact, neutral as different): about 310,000 first-person persona sentence pairs; the verified test set is checked by three people | `dnli.zip` (SHA-256 `1164b0d9…5e42`, matching ParlAI's checksum for the original) | Original Google Drive link from [the project page](https://wellecks.com/dialogue_nli/) returns 404; the identical zip comes from [Hugging Face, xksteven/dialogue_nli](https://huggingface.co/datasets/xksteven/dialogue_nli) | None stated. **Private labels only** |
| **Synthetic-Persona-Chat** (Google) | `acceptance` (lines stating a persona fact against small talk) and `relevance` (a real reply against one from another conversation): 10,906 conversations with both speakers' persona lists, plus 11,001 with new personas | `spc_*.csv` | [Hugging Face, google/Synthetic-Persona-Chat](https://huggingface.co/datasets/google/Synthetic-Persona-Chat) | CC BY 4.0 (attribute Google) |
| **Multi-Session Chat (MSC) v0.1** | `acceptance`: the persona summaries (`msc_personasummary`) list the facts each speaker revealed in a session, a ready-made "worth remembering" label; facts that change between sessions give some `update` pairs | `msc_v0.1.tar.gz` | [ParlAI](https://parl.ai/projects/msc/), `dl.fbaipublicfiles.com/parlai/msc/msc_v0.1.tar.gz` | None stated. **Private labels only** |
| **LongMemEval** (cleaned) | **Testing only, never training.** 500 questions over long chat histories, 78 of them `knowledge-update`. Turns holding the evidence are marked `has_answer: true` (tests `acceptance`); knowledge-update questions test `update` | `longmemeval_oracle.json` (evidence sessions only), `longmemeval_s_cleaned.json` (about 115k-token histories). The 2.7 GB `_m` version isn't needed | [Hugging Face, xiaowu0162/longmemeval-cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned); [repository](https://github.com/xiaowu0162/LongMemEval) | MIT |

Downloaded: 783 MB in total. Unpacked, Dialogue NLI's core files are about 103 MB (its optional
"extra" set is about 900 MB more and isn't needed); MSC is 214 MB.

Considered and not used: SNLI (captions, not personal facts; ShareAlike), MultiNLI (mixed
licences), ANLI, LoCoMo, MemUse and DailyDialog (non-commercial licences, and small or without
memory labels), Quora Question Pairs (Quora's terms), STS Benchmark (unclear licence; graded
scores don't fit these labels).
