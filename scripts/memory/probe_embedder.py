"""Probe a multimodal embedder for SORA's memory manager (MEMORY_MANAGER_2026-10-08 step 1).

    uv run python scripts/memory/probe_embedder.py
    uv run python scripts/memory/probe_embedder.py --model <gguf> --mmproj <gguf> ^
        --server <llama-server.exe>

Starts llama-server with the embedding model, embeds training/memory/embedder_probe.json and
reports what the memory design depends on:

  A. text recall    -- does a differently worded question find its memory? (rank 1, top 3, MRR),
                       with and without EmbeddingGemma's task prefixes, at 768 / 512 / 256 dims;
  B. relation bands -- similarity for same fact / updated fact / related / unrelated pairs, the
                       bands the network's links and "superseded" rule need;
  C. image <-> text -- does each caption find its image, and each image its caption?
  D. audio <-> text -- does a spoken memory find its written memory?
  E. speed          -- milliseconds per text, image and audio embedding (warm).

A JSON report goes to .local/memory-probe/. Nothing is stored in SORA.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import subprocess
import time
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path.home() / ("AppData/Local/Temp/claude/C--Users-oscar-Desktop-SORA/"
                         "504b0065-6006-578e-85bd-9591a537cc00/scratchpad")
OUT = ROOT / ".local/memory-probe"
PORT = 18881

Vector = list[float]


def unit(vector: Vector, dims: int | None = None) -> Vector:
    """Truncate (Matryoshka) and re-normalise, as the model card requires."""
    v = vector[:dims] if dims else vector
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def cos(a: Vector, b: Vector) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class Embedder:
    def __init__(self, server: Path, model: Path, mmproj: Path, ngl: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        self.log = (OUT / "llama-server.log").open("w")
        self.process = subprocess.Popen(
            [str(server), "-m", str(model), "--mmproj", str(mmproj), "--embeddings",
             "--pooling", "mean", "-c", "8192", "-b", "8192", "-ub", "8192", "--parallel", "1",
             "-ngl", ngl, "--host", "127.0.0.1", "--port", str(PORT)],
            stdout=self.log, stderr=subprocess.STDOUT, creationflags=0x08000000,
        )
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=300)
        for _ in range(180):
            try:
                if self.http.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if self.process.poll() is not None:
                raise SystemExit("llama-server exited; see .local/memory-probe/llama-server.log")
            time.sleep(1)
        props = self.http.get("/props").json()
        self.marker = props["media_marker"]  # random per server run
        self.modalities = props.get("modalities", {})
        self.times: dict[str, list[float]] = {"text": [], "image": [], "audio": []}

    def _embed(self, content: object, kind: str) -> Vector:
        started = time.perf_counter()
        reply = self.http.post("/embeddings", json={"content": content})
        reply.raise_for_status()
        self.times[kind].append((time.perf_counter() - started) * 1000)
        data = reply.json()
        embedding = (data[0] if isinstance(data, list) else data["data"][0])["embedding"]
        vector = embedding[0] if isinstance(embedding[0], list) else embedding
        if any(math.isnan(x) for x in vector):
            raise SystemExit(f"NaN in a {kind} embedding (float16 overflow?)")
        return unit(vector)

    def text(self, value: str) -> Vector:
        return self._embed(value, "text")

    def media(self, path: Path, kind: str) -> Vector:
        data = base64.b64encode(path.read_bytes()).decode()
        return self._embed([{"prompt_string": self.marker, "multimodal_data": [data]}], kind)

    def close(self) -> None:
        self.process.kill()
        self.process.wait()
        self.log.close()


def ranks(queries: list[Vector], corpus: list[Vector], wanted: list[int]) -> list[int]:
    found = []
    for query, target in zip(queries, wanted, strict=True):
        scores = [cos(query, item) for item in corpus]
        found.append(1 + sum(1 for s in scores if s > scores[target]))
    return found


def summary(found: list[int]) -> dict[str, float]:
    return {"rank1": round(sum(r == 1 for r in found) / len(found), 3),
            "top3": round(sum(r <= 3 for r in found) / len(found), 3),
            "mrr": round(mean(1 / r for r in found), 3)}


def speak(texts: dict[str, str]) -> dict[str, Path]:
    """Windows' built-in voice reads each memory into a mono 16 kHz WAV."""
    folder = OUT / "spoken"
    folder.mkdir(parents=True, exist_ok=True)
    paths = {key: folder / f"{key}.wav" for key in texts}
    script = ["Add-Type -AssemblyName System.Speech",
              "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo 16000, "
              "([System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen), "
              "([System.Speech.AudioFormat.AudioChannel]::Mono)"]
    for key, text in texts.items():
        if not paths[key].exists():
            script += ["$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                       f"$s.SetOutputToWaveFile('{paths[key]}', $f)",
                       "$s.Speak('" + text.replace("'", "''") + "'); $s.Dispose()"]
    subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(script)], check=True)
    return paths


def run(args: argparse.Namespace) -> dict[str, Any]:
    probe = json.loads((ROOT / "training/memory/embedder_probe.json").read_text("utf-8"))
    memories, questions = probe["memories"], probe["questions"]
    index = {m["id"]: i for i, m in enumerate(memories)}
    embed = Embedder(args.server, args.model, args.mmproj, args.ngl)
    report: dict[str, Any] = {"model": str(args.model), "mmproj": str(args.mmproj),
                              "modalities": embed.modalities, "memories": len(memories)}
    try:
        # A. Text recall, with the card's asymmetric search prefixes and without any.
        styles = {
            "prefixed": ("task: search result | query: {}", "title: none | text: {}"),
            "plain": ("{}", "{}"),
        }
        recall: dict[str, Any] = {}
        raw: dict[str, tuple[list[Vector], list[Vector]]] = {}
        for style, (query_form, doc_form) in styles.items():
            corpus = [embed.text(doc_form.format(m["text"])) for m in memories]
            asked = [embed.text(query_form.format(q["text"])) for q in questions]
            raw[style] = (asked, corpus)
        wanted = [index[q["id"]] for q in questions]
        for style, (asked, corpus) in raw.items():
            for dims in (768, 512, 256):
                found = ranks([unit(v, dims) for v in asked], [unit(v, dims) for v in corpus],
                              wanted)
                recall[f"{style}-{dims}"] = summary(found)
            found = ranks(asked, corpus, wanted)
            recall[f"{style}-misses"] = [
                {"question": q["text"], "rank": r, "owner": memories[index[q["id"]]].get("owner",
                                                                                         False)}
                for q, r in zip(questions, found, strict=True) if r > 1]
            owner = [r for q, r in zip(questions, found, strict=True)
                     if memories[index[q["id"]]].get("owner")]
            recall[f"{style}-owner-ranks"] = owner
        report["A_text_recall"] = recall

        # B. Relation bands (symmetric similarity prefix on both sides).
        bands: dict[str, list[float]] = {}
        for pair in probe["pairs"]:
            a = embed.text("task: sentence similarity | query: " + pair["a"])
            b = embed.text("task: sentence similarity | query: " + pair["b"])
            bands.setdefault(pair["label"], []).append(round(cos(a, b), 3))
        report["B_bands"] = {label: {"min": min(v), "mean": round(mean(v), 3), "max": max(v),
                                     "values": v} for label, v in bands.items()}

        # C. Image <-> caption.
        images, captions, names = [], [], []
        for item in probe["images"]:
            path = (ROOT / item["file"]) if "file" in item else (SCRATCH / item["scratch"])
            if not path.is_file():
                continue
            images.append(embed.media(path, "image"))
            captions.append(embed.text("task: search result | query: " + item["caption"]))
            names.append(path.name)
        if images:
            caption_ranks = ranks(captions, images, list(range(len(images))))
            image_ranks = ranks(images, captions, list(range(len(images))))
            matrix = [[round(cos(c, i), 3) for i in images] for c in captions]
            report["C_image_text"] = {
                "images": names, "caption_finds_image": summary(caption_ranks),
                "image_finds_caption": summary(image_ranks),
                "caption_ranks": dict(zip(names, caption_ranks, strict=True)),
                "matched_mean": round(mean(matrix[i][i] for i in range(len(names))), 3),
                "unmatched_mean": round(mean(matrix[i][j] for i in range(len(names))
                                             for j in range(len(names)) if i != j), 3),
            }

        # D. Spoken memory -> written memory.
        spoken = speak({key: memories[index[key]]["text"] for key in probe["spoken"]})
        corpus = [embed.text("title: none | text: " + m["text"]) for m in memories]
        clips = [embed.media(path, "audio") for path in spoken.values()]
        audio_ranks = ranks(clips, corpus, [index[key] for key in spoken])
        report["D_audio_text"] = {"clips": list(spoken), **summary(audio_ranks),
                                  "ranks": dict(zip(spoken, audio_ranks, strict=True))}

        # E. Speed (first call of each kind excluded as warm-up).
        report["E_speed_ms"] = {kind: round(mean(t[1:] or t), 1)
                                for kind, t in embed.times.items() if t}
    finally:
        embed.close()
    report["probed_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def main() -> None:
    models = ROOT / ".local/models/embeddinggemma-2"
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--model", type=Path,
                        default=models / "embeddinggemma-2-UD-Q4_K_XL.gguf")
    parser.add_argument("--mmproj", type=Path, default=models / "mmproj-Q8_0.gguf")
    parser.add_argument("--server", type=Path,
                        default=ROOT / ".local/llama.cpp-b11516/llama-server.exe")
    parser.add_argument("--ngl", default="99", help="GPU layers (0 = CPU only)")
    args = parser.parse_args()
    report = run(args)
    target = OUT / f"report-{datetime.now():%Y%m%d-%H%M%S}.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "B_bands"}, indent=1)[:6000])
    for label, band in report["B_bands"].items():
        print(f"band {label:9} min {band['min']:.3f} mean {band['mean']:.3f} max {band['max']:.3f}")
    print(f"report: {target}")


if __name__ == "__main__":
    main()
