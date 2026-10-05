"""Direct-argv content handler used by the P15.7 local UI acceptance fixture."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    output = Path(sys.argv[1])
    path, verb, reference_id = sys.argv[2:5]
    output.write_text(
        json.dumps({"path": path, "verb": verb, "reference_id": reference_id}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
