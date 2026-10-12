"""Test each place the memory manager uses EmbeddingGemma 2, through Core's own code.

    uv run python scripts/memory/probe_use_cases.py [--cpu]

Uses sora.memory.embedder (the class Core runs), sora.memory.features and sora.memory.layers, so
what passes here is what the pipeline does. Data: training/memory/embedder_probe.json (30 stored
memories, 30 questions, 19 labelled pairs, 9 images) and training/memory/use_case_probe.json.

  U1  recall: does a question find its memory, and do off-topic messages stay below a floor?
      Compared with today's recall (the 10 most recent memories).
  U2  follow-ups: "what does she hate?" after "did I tell you about my sister?"
  U3  acceptance, repeats: is a repeat's nearest memory clearly closer than a new fact's?
  U4  acceptance, worth keeping: lasting facts against chatter, by prototype similarity.
  U5  part relevance: her reply or a read result about the owner's words, against unrelated ones.
  U6  images: the owner's message about an image against an unrelated message; near-duplicate
      images (JPEG at quality 85, half size, a 70% crop) against different images.
  U7  comparison layers: leave-one-out training of same_subject and update on 41 labelled pairs,
      against similarity-only baselines (this also exercises the training code).
  U8  goals: does a goal find the memories that serve it?
  U9  her own thoughts: does "what's my favourite colour?" find the owner's fact, not her own
      opinion? Plain stored text against author-labelled document titles.
  U10 map: PCA 2D/3D positions; how many of each memory's 5 nearest neighbours survive.
  U11 speed: one query embedding (per message) and one stored document.

A JSON report goes to .local/memory-probe/. Nothing is stored in SORA.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from sora.memory import features
from sora.memory.embedder import EmbedderConfig, LlamaEmbedder
from sora.memory.layers import fit
from sora.memory.vectors import Vector, cosine, project, top_k

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".local/memory-probe"
SCRATCH = Path.home() / ("AppData/Local/Temp/claude/C--Users-oscar-Desktop-SORA/"
                         "504b0065-6006-578e-85bd-9591a537cc00/scratchpad")


def auc(positives: list[float], negatives: list[float]) -> float:
    if not positives or not negatives:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return round(wins / (len(positives) * len(negatives)), 3)


def best_cut(positives: list[float], negatives: list[float]) -> dict[str, float]:
    """The threshold with the best balanced accuracy, and what it gets."""
    best = (0.0, 0.0)
    for cut in sorted(set(positives + negatives)):
        tpr = sum(p >= cut for p in positives) / len(positives)
        tnr = sum(n < cut for n in negatives) / len(negatives)
        if (tpr + tnr) / 2 > best[1]:
            best = (cut, (tpr + tnr) / 2)
    return {"threshold": round(best[0], 3), "balanced_accuracy": round(best[1], 3)}


def spread(values: list[float]) -> dict[str, float]:
    return {"min": round(min(values), 3), "median": round(median(values), 3),
            "max": round(max(values), 3)}


def image_variants(paths: list[Path]) -> list[dict[str, Path]]:
    """JPEG q85, half size and a centre 70% crop of each image (System.Drawing)."""
    folder = OUT / "variants"
    folder.mkdir(parents=True, exist_ok=True)
    result, script = [], ["Add-Type -AssemblyName System.Drawing",
                          "$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() "
                          "| Where-Object MimeType -eq 'image/jpeg'",
                          "$q = New-Object System.Drawing.Imaging.EncoderParameters 1",
                          "$q.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter "
                          "([System.Drawing.Imaging.Encoder]::Quality), 85L"]
    for index, path in enumerate(paths):
        names = {kind: folder / f"{index}-{kind}.jpg" for kind in ("jpeg", "half", "crop")}
        result.append(names)
        if all(p.exists() for p in names.values()):
            continue
        script += [
            f"$i = [System.Drawing.Image]::FromFile('{path}')",
            f"$i.Save('{names['jpeg']}', $codec, $q)",
            "$h = New-Object System.Drawing.Bitmap $i, ([int]($i.Width/2)), ([int]($i.Height/2))",
            f"$h.Save('{names['half']}', $codec, $q); $h.Dispose()",
            "$w = [int]($i.Width*0.7); $t = [int]($i.Height*0.7)",
            "$r = New-Object System.Drawing.Rectangle ([int](($i.Width-$w)/2)), "
            "([int](($i.Height-$t)/2)), $w, $t",
            "$c = (New-Object System.Drawing.Bitmap $i).Clone($r, $i.PixelFormat)",
            f"$c.Save('{names['crop']}', $codec, $q); $c.Dispose(); $i.Dispose()",
        ]
    if len(script) > 4:
        subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(script)], check=True)
    return result


async def run(cpu: bool) -> dict[str, Any]:
    base = json.loads((ROOT / "training/memory/embedder_probe.json").read_text("utf-8"))
    cases = json.loads((ROOT / "training/memory/use_case_probe.json").read_text("utf-8"))
    models = ROOT / ".local/models/embeddinggemma-2"
    embedder = LlamaEmbedder(EmbedderConfig(
        server=ROOT / ".local/llama.cpp-b11516/llama-server.exe",
        model=models / "embeddinggemma-2-UD-Q4_K_XL.gguf", mmproj=models / "mmproj-Q8_0.gguf",
        gpu_layers="0" if cpu else "99", log=OUT / "embedder.log"))
    report: dict[str, Any] = {"embedder": embedder.identity, "device": "cpu" if cpu else "gpu"}
    memories = base["memories"]
    ids = [m["id"] for m in memories]
    text = {m["id"]: m["text"] for m in memories}
    th = features.Thresholds()
    try:
        await embedder.start()
        doc = {i: await embedder.embed(text[i], "document") for i in ids}
        sim = {i: await embedder.embed(text[i], "similarity") for i in ids}
        stored = list(doc.items())

        # U1 recall with a floor, against today's "10 most recent".
        on_topic, hits, recency_hits, ranks = [], 0, 0, []
        recent = set(ids[-10:])
        for question in base["questions"]:
            q = await embedder.embed(question["text"], "query")
            ranked = top_k(q, stored, k=len(stored))
            target = question["id"]
            score = dict(ranked)[target]
            on_topic.append(score)
            rank = [k for k, _ in ranked].index(target) + 1
            ranks.append(rank)
            hits += rank <= th.recall_limit and score >= th.recall_floor
            recency_hits += target in recent
        off_topic = []
        for message in cases["off_topic"]:
            q = await embedder.embed(message, "query")
            off_topic.append(top_k(q, stored, k=1)[0][1])
        report["U1_recall"] = {
            "target_similarity": spread(on_topic), "off_topic_best_similarity": spread(off_topic),
            "auc": auc(on_topic, off_topic), "floor": best_cut(on_topic, off_topic),
            "rank1": round(sum(r == 1 for r in ranks) / len(ranks), 3),
            "meaning_recall_in_10_above_floor": round(hits / len(ranks), 3),
            "today_recency_10_contains_target": round(recency_hits / len(ranks), 3),
            "off_topic_above_floor": sum(s >= th.recall_floor for s in off_topic),
        }

        # U2 follow-ups: the message alone, and with the previous message.
        alone, joined = [], []
        for case in cases["follow_ups"]:
            for form, bucket in ((case["message"], alone),
                                 (case["previous"] + " " + case["message"], joined)):
                q = await embedder.embed(form, "query")
                ranked = [k for k, _ in top_k(q, stored, k=len(stored))]
                bucket.append(ranked.index(case["id"]) + 1)
        report["U2_follow_ups"] = {
            "message_alone_ranks": alone, "with_previous_ranks": joined,
            "alone_rank1": sum(r == 1 for r in alone), "joined_rank1": sum(r == 1 for r in joined),
            "of": len(alone)}

        # U3 acceptance: nearest stored memory for repeats against new facts.
        sims = list(sim.items())
        repeat_near, repeat_right = [], 0
        for case in cases["repeats"]:
            v = await embedder.embed(case["text"], "similarity")
            best = top_k(v, sims, k=1)[0]
            repeat_near.append(best[1])
            repeat_right += best[0] == case["id"]
        novel_near = [top_k(await embedder.embed(t, "similarity"), sims, k=1)[0][1]
                      for t in cases["novel"]]
        report["U3_repeats"] = {"repeat_nearest": spread(repeat_near),
                                "repeat_found_its_memory": f"{repeat_right}/{len(repeat_near)}",
                                "novel_nearest": spread(novel_near),
                                "auc": auc(repeat_near, novel_near),
                                "cut": best_cut(repeat_near, novel_near)}

        # U4 worth keeping: prototype margin (personal - chatter).
        personal = [await embedder.embed(t, "similarity") for t in features.PERSONAL]
        chatter = [await embedder.embed(t, "similarity") for t in features.CHATTER]

        async def margin(t: str) -> float:
            v = await embedder.embed(t, "similarity")
            return (features.prototype_score(v, personal)
                    - features.prototype_score(v, chatter))

        worth = [await margin(t) for t in cases["worth"]]
        chat = [await margin(t) for t in cases["chatter"]]
        report["U4_worth_keeping"] = {
            "worth_margin": spread(worth), "chatter_margin": spread(chat), "auc": auc(worth, chat),
            "at_zero": round((sum(w > 0 for w in worth) + sum(c <= 0 for c in chat))
                             / (len(worth) + len(chat)), 3),
            "cut": best_cut(worth, chat)}

        # U5 part relevance (text parts).
        relevant, irrelevant = [], []
        for entry in cases["parts"]:
            owner = await embedder.embed(entry["owner"], "similarity")
            for part in entry["relevant"]:
                relevant.append(cosine(await embedder.embed(part, "similarity"), owner))
            for part in entry["irrelevant"]:
                irrelevant.append(cosine(await embedder.embed(part, "similarity"), owner))
        report["U5_part_relevance"] = {
            "relevant": spread(relevant), "irrelevant": spread(irrelevant),
            "auc": auc(relevant, irrelevant), "cut": best_cut(relevant, irrelevant),
            "fixed_threshold": th.part_relevance,
            "fixed_accuracy": round((sum(r >= th.part_relevance for r in relevant)
                                     + sum(i < th.part_relevance for i in irrelevant))
                                    / (len(relevant) + len(irrelevant)), 3)}

        # U6 images: relevance to the owner's message, and near-duplicates.
        paths = []
        for item in base["images"]:
            path = ROOT / item["file"] if "file" in item else SCRATCH / item["scratch"]
            paths.append(path if path.is_file() else None)
        available = [p for p in paths if p is not None]
        image_vec = {p: await embedder.embed_media(p.read_bytes(), "image") for p in available}
        rel_img, irr_img = [], []
        for case in cases["image_messages"]:
            path = paths[case["image"]]
            if path is None:
                continue
            rel_img.append(cosine(await embedder.embed(case["relevant"], "query"), image_vec[path]))
            irr_img.append(cosine(await embedder.embed(case["irrelevant"], "query"),
                                  image_vec[path]))
        variants = image_variants(available)
        same, others = {"jpeg": [], "half": [], "crop": []}, []
        for path, names in zip(available, variants, strict=True):
            for kind, variant in names.items():
                vec = await embedder.embed_media(variant.read_bytes(), "image")
                same[kind].append(cosine(vec, image_vec[path]))
            others += [cosine(image_vec[path], image_vec[o]) for o in available if o != path]
        report["U6_images"] = {
            "images": len(available),
            "relevant_message": spread(rel_img), "irrelevant_message": spread(irr_img),
            "message_auc": auc(rel_img, irr_img),
            "near_duplicate": {k: spread(v) for k, v in same.items()},
            "different_images": spread(others),
            "duplicate_cut": best_cut([x for v in same.values() for x in v], others)}

        # U7 comparison layers: leave-one-out on all labelled pairs.
        pairs = [dict(p, days=p.get("days", 10)) for p in base["pairs"]] + cases["pairs_extra"]
        rows = []
        for pair in pairs:
            a = await embedder.embed(pair["a"], "similarity")
            b = await embedder.embed(pair["b"], "similarity")
            values = features.comparison(pair["b"], pair["a"], cosine(a, b), pair["days"])
            rows.append((values, pair["label"]))

        def loo(name: str, data: list[tuple[dict[str, float], int]],
                baseline: Any) -> dict[str, Any]:
            right = base_right = 0
            for i in range(len(data)):
                train = [(v, y, 1.0) for j, (v, y) in enumerate(data) if j != i]
                layer = fit(name, train, features.FEATURES[name])
                right += layer.decide(data[i][0]) == bool(data[i][1])
                base_right += bool(baseline(data[i][0])) == bool(data[i][1])
            return {"examples": len(data), "trained_loo_accuracy": round(right / len(data), 3),
                    "baseline_accuracy": round(base_right / len(data), 3)}

        subject = [(v, int(label in ("same", "updated"))) for v, label in rows]
        update = [(v, int(label == "updated")) for v, label in rows
                  if label in ("same", "updated")]
        report["U7_comparison"] = {
            "bands": {lab: spread([v["similarity"] for v, label in rows if label == lab])
                      for lab in ("same", "updated", "related", "unrelated")},
            "same_subject": loo("same_subject", subject,
                                lambda v: v["similarity"] >= th.same_subject),
            "update": loo("update", update, lambda v: v["change_marker"] or
                          v["number_mismatch"] or v["negation_mismatch"]),
        }

        # U8 goals: does each goal find the memories that serve it?
        goal_rows = {}
        for case in cases["goals"]:
            g = await embedder.embed(case["goal"], "query")
            scores = {i: cosine(g, doc[i]) for i in ids}
            pos = [scores[i] for i in case["supporting"]]
            neg = [scores[i] for i in ids if i not in case["supporting"]]
            top = [k for k, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:5]]
            goal_rows[case["goal"][:40]] = {"auc": auc(pos, neg),
                                            "top5_supporting": sum(t in case["supporting"]
                                                                   for t in top)}
        report["U8_goals"] = {"goals": goal_rows,
                              "mean_auc": round(mean(r["auc"] for r in goal_rows.values()), 3)}

        # U9 her own thoughts beside the owner's facts: plain documents, then author titles.
        u9 = {}
        for form, (owner_title, own_title) in {"plain": ("none", "none"),
                                               "titled": ("the owner told me",
                                                          "my own thought")}.items():
            corpus = [(i, await embedder.embed(text[i], "document", title=owner_title))
                      for i in ids]
            corpus += [(f"own-{n}", await embedder.embed(c["thought"], "document",
                                                         title=own_title))
                       for n, c in enumerate(cases["own_thoughts"])]
            right = 0
            for case in cases["own_thoughts"]:
                q = await embedder.embed(case["query"], "query")
                right += top_k(q, corpus, k=1)[0][0] == case["owner"]
            u9[form] = f"{right}/{len(cases['own_thoughts'])} owner facts ranked above her thought"
        report["U9_own_thoughts"] = u9

        # U10 map projection.
        vectors = [sim[i] for i in ids]
        u10 = {}
        for dims in (2, 3):
            points = project(vectors, dims)
            kept = []
            for i in range(len(ids)):
                full = {j for j, _ in top_k(vectors[i], [(str(j), v) for j, v in
                                                         enumerate(vectors)], k=6)} - {str(i)}
                near = sorted(range(len(ids)), key=lambda j: sum(
                    (a - b) ** 2 for a, b in zip(points[i], points[j], strict=True)))[1:6]
                kept.append(len(full & {str(j) for j in near}) / 5)
            u10[f"{dims}d_neighbours_kept"] = round(mean(kept), 3)
        report["U10_map"] = u10

        # U11 speed (warm).
        timings: dict[str, list[float]] = {"query": [], "document": [], "image": []}
        for message in cases["off_topic"][:10]:
            started = time.perf_counter()
            await embedder.embed(message, "query")
            timings["query"].append((time.perf_counter() - started) * 1000)
        for item in cases["novel"]:
            started = time.perf_counter()
            await embedder.embed(item, "document")
            timings["document"].append((time.perf_counter() - started) * 1000)
        for path in available[:3]:
            started = time.perf_counter()
            await embedder.embed_media(path.read_bytes(), "image")
            timings["image"].append((time.perf_counter() - started) * 1000)
        report["U11_speed_ms"] = {k: round(median(v), 1) for k, v in timings.items() if v}
        report["U11_compare_5000_ms"] = round(_compare_time(), 1)
    finally:
        await embedder.close()
    report["probed_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def _compare_time() -> float:
    import random

    rng = random.Random(1)
    query: Vector = [rng.uniform(-1, 1) for _ in range(512)]
    items = [(str(i), [rng.uniform(-1, 1) for _ in range(512)]) for i in range(5000)]
    started = time.perf_counter()
    top_k(query, items, k=10)
    return (time.perf_counter() - started) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--cpu", action="store_true", help="run the embedder on the CPU")
    report = asyncio.run(run(parser.parse_args().cpu))
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"use-cases-{datetime.now():%Y%m%d-%H%M%S}.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=1))
    print("report:", target)


if __name__ == "__main__":
    main()
