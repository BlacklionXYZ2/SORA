from __future__ import annotations

from pathlib import Path

EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "contracts" / "examples" / "v1"


def example_text(category: str, name: str) -> str:
    return (EXAMPLE_ROOT / category / name).read_text(encoding="utf-8")
