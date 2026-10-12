"""The memory manager's small trained layers: logistic models over named features.

Each layer is a few hundred bytes of JSON: feature names, standardisation, weights, a decision
threshold, and how it scored when trained. They train on the CPU in seconds (``fit``), with no
numpy. Every version is kept under ``<state>/memory/layers/<name>/``; ``active.json`` names the
one in use, so rolling back is pointing it at an older file. With no active file, the manager
uses its fixed thresholds (``sora.memory.features.Thresholds``).
"""

from __future__ import annotations

import json
import math
import os
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sora.memory.features import FEATURES

Example = tuple[Mapping[str, float], int, float]  # features, label (0/1), weight


@dataclass(frozen=True)
class LogisticLayer:
    name: str
    version: str
    features: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    threshold: float = 0.5
    trained_at: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def probability(self, values: Mapping[str, float]) -> float:
        z = self.bias + sum(
            weight * ((float(values.get(name, 0.0)) - mean) / scale)
            for name, mean, scale, weight in zip(
                self.features, self.means, self.scales, self.weights, strict=True)
        )
        return 1 / (1 + math.exp(-max(-40.0, min(40.0, z))))

    def decide(self, values: Mapping[str, float]) -> bool:
        return self.probability(values) >= self.threshold

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> LogisticLayer:
        data = json.loads(text)
        for key in ("features", "means", "scales", "weights"):
            data[key] = tuple(data[key])
        layer = cls(**data)
        if not (len(layer.features) == len(layer.means) == len(layer.scales)
                == len(layer.weights)):
            raise ValueError("layer file is inconsistent")
        if layer.name in FEATURES and set(layer.features) - set(FEATURES[layer.name]):
            raise ValueError(f"layer {layer.name} uses features Core no longer computes")
        return layer


def fit(
    name: str, examples: Sequence[Example], feature_names: Sequence[str], *,
    epochs: int = 400, rate: float = 0.1, l2: float = 0.01, seed: int = 7,
) -> LogisticLayer:
    """Weighted logistic regression by full-batch gradient descent on standardised features.

    Classes are balanced by weight, so a layer with few "drop" labels still learns them.
    """
    if not examples:
        raise ValueError("no examples")
    columns = [[float(values.get(n, 0.0)) for values, _, _ in examples] for n in feature_names]
    means = [sum(column) / len(column) for column in columns]
    scales = [math.sqrt(sum((v - m) ** 2 for v in column) / len(column)) or 1.0
              for column, m in zip(columns, means, strict=True)]
    rows = [[(columns[j][i] - means[j]) / scales[j] for j in range(len(feature_names))]
            for i in range(len(examples))]
    labels = [label for _, label, _ in examples]
    positives = sum(w for (_, label, w) in examples if label == 1) or 1.0
    negatives = sum(w for (_, label, w) in examples if label == 0) or 1.0
    total = positives + negatives
    weights_per = [w * (total / (2 * (positives if label == 1 else negatives)))
                   for (_, label, w) in examples]
    rng = random.Random(seed)
    weights = [rng.uniform(-0.01, 0.01) for _ in feature_names]
    bias = 0.0
    norm = sum(weights_per)
    for _ in range(epochs):
        grad = [0.0] * len(weights)
        grad_bias = 0.0
        for row, label, weight in zip(rows, labels, weights_per, strict=True):
            z = bias + math.sumprod(weights, row)
            error = (1 / (1 + math.exp(-max(-40.0, min(40.0, z)))) - label) * weight
            grad_bias += error
            for j, value in enumerate(row):
                grad[j] += error * value
        bias -= rate * grad_bias / norm
        weights = [w - rate * (g / norm + l2 * w) for w, g in zip(weights, grad, strict=True)]
    return LogisticLayer(name=name, version="", features=tuple(feature_names),
                         means=tuple(means), scales=tuple(scales), weights=tuple(weights),
                         bias=bias)


class LayerSet:
    """The active version of each layer in a state folder (or none: fixed thresholds)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.layers: dict[str, LogisticLayer] = {}
        self.reload()

    def reload(self) -> None:
        self.layers = {}
        for name in FEATURES:
            pointer = self.root / name / "active.json"
            try:
                version = json.loads(pointer.read_text("utf-8"))["version"]
                self.layers[name] = LogisticLayer.from_json(
                    (self.root / name / f"{version}.json").read_text("utf-8"))
            except (OSError, ValueError, KeyError, TypeError):
                continue  # no trained layer, or an unreadable one: fixed thresholds

    def get(self, name: str) -> LogisticLayer | None:
        return self.layers.get(name)

    def policy(self, name: str) -> str:
        layer = self.layers.get(name)
        return f"layer:{layer.version}" if layer else "fixed-threshold"

    def save(self, layer: LogisticLayer, *, activate: bool) -> Path:
        folder = self.root / layer.name
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{layer.version}.json"
        target.write_text(layer.to_json(), encoding="utf-8")
        if activate:
            self.activate(layer.name, layer.version)
        return target

    def activate(self, name: str, version: str) -> None:
        """Point ``active.json`` at a saved version (also how a rollback is done)."""
        folder = self.root / name
        if not (folder / f"{version}.json").is_file():
            raise ValueError(f"{name} has no saved version {version}")
        pointer = folder / "active.json"
        partial = pointer.with_suffix(".partial")
        partial.write_text(json.dumps({"version": version}), encoding="utf-8")
        os.replace(partial, pointer)
        self.reload()

    def versions(self, name: str) -> list[str]:
        folder = self.root / name
        return sorted(p.stem for p in folder.glob("*.json") if p.stem != "active") \
            if folder.is_dir() else []
