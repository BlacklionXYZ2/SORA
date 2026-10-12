"""Vector maths for memory embeddings, with the standard library only.

Core has no numpy. ``math.sumprod`` (C, Python 3.12) scores a 512-dimension pair in microseconds,
so comparing one memory with 5,000 others takes about 25 ms. Vectors are stored as float32 BLOBs.
"""

from __future__ import annotations

import math
from array import array
from collections.abc import Iterable, Sequence

Vector = list[float]


def unit(values: Sequence[float], dims: int | None = None) -> Vector:
    """Truncate (Matryoshka) and re-normalise, as EmbeddingGemma's model card requires."""
    kept = list(values[:dims] if dims else values)
    norm = math.sqrt(math.sumprod(kept, kept)) or 1.0
    return [value / norm for value in kept]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Similarity of two unit vectors."""
    return math.sumprod(a, b)


def pack(vector: Sequence[float]) -> bytes:
    return array("f", vector).tobytes()


def unpack(blob: bytes) -> Vector:
    values = array("f")
    values.frombytes(blob)
    return values.tolist()


def mean_vector(vectors: Sequence[Sequence[float]]) -> Vector:
    return unit([sum(column) / len(vectors) for column in zip(*vectors, strict=True)])


def top_k(
    query: Sequence[float], items: Iterable[tuple[str, Sequence[float]]], k: int,
    *, floor: float | None = None, exclude: frozenset[str] = frozenset(),
) -> list[tuple[str, float]]:
    """The k most similar items (best score per key), highest first, above an optional floor."""
    best: dict[str, float] = {}
    for key, vector in items:
        if key in exclude:
            continue
        score = cosine(query, vector)
        if (floor is None or score >= floor) and score > best.get(key, -2.0):
            best[key] = score
    return sorted(best.items(), key=lambda item: item[1], reverse=True)[:k]


def project(vectors: Sequence[Sequence[float]], dims: int = 2,
            iterations: int = 60) -> list[tuple[float, ...]]:
    """PCA coordinates for the memory map: stable and repeatable (power iteration, fixed start).

    Neighbours and links always come from the full vectors; this is only for drawing.
    """
    if not vectors:
        return []
    width = len(vectors[0])
    centre = [sum(column) / len(vectors) for column in zip(*vectors, strict=True)]
    rows = [[value - mean for value, mean in zip(vector, centre, strict=True)]
            for vector in vectors]
    components: list[Vector] = []
    for index in range(min(dims, width)):
        direction = unit([1.0 / (1 + ((position + index) % 7)) for position in range(width)])
        for _ in range(iterations):
            # covariance · direction, without forming the covariance matrix
            scores = [math.sumprod(row, direction) for row in rows]
            moved = [math.sumprod(scores, column) for column in zip(*rows, strict=True)]
            for component in components:  # deflate: stay orthogonal to earlier components
                overlap = math.sumprod(moved, component)
                moved = [m - overlap * c for m, c in zip(moved, component, strict=True)]
            if not any(moved):
                break
            direction = unit(moved)
        components.append(direction)
    return [tuple(math.sumprod(row, component) for component in components) for row in rows]
