"""Write or verify the committed JSON Schemas for public SORA contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sora.contracts.registry import PUBLIC_CONTRACTS


def rendered_schema(model_name: str) -> str:
    model = PUBLIC_CONTRACTS[model_name]
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if committed schemas are stale")
    args = parser.parse_args()
    schema_root = Path(__file__).resolve().parents[1] / "contracts" / "schema" / "v1"

    stale: list[str] = []
    if not args.check:
        schema_root.mkdir(parents=True, exist_ok=True)

    for name in sorted(PUBLIC_CONTRACTS):
        path = schema_root / f"{name}.schema.json"
        rendered = rendered_schema(name)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != rendered:
                stale.append(path.name)
        else:
            path.write_text(rendered, encoding="utf-8")

    if stale:
        print("stale or missing contract schemas: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
