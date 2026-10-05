"""Hash the GUI starting source without reading owner state or credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sora.runtime.app_settings import FIELDS, AppSettings

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {"bin", "obj", "Library", "Temp", "Logs", "Builds", "UserSettings", "__pycache__"}
SUFFIXES = {".py", ".cs", ".csproj", ".ps1", ".md", ".json", ".js", ".css", ".html"}


def capture(output: Path) -> dict[str, object]:
    output = output.resolve()
    if not output.is_relative_to(ROOT / ".local"):
        raise ValueError("Evidence must be written to a dedicated repository .local directory")
    if output.exists():
        raise ValueError("Baseline exists; use a new filename to preserve previous evidence")
    files: dict[str, str] = {}
    for folder in ("src", "clients", "scripts", "contracts/schema", "docs/gui/reference"):
        for path in (ROOT / folder).rglob("*"):
            relative = path.relative_to(ROOT)
            if (path.is_file() and not path.is_symlink()
                    and not EXCLUDE.intersection(relative.parts) and path.suffix in SUFFIXES):
                files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("SORA_GUI_IMPLEMENTATION_ROADMAP.md", "SORA_IMPLEMENTATION_PLAN.md",
                 "SORA_OVERVIEW.md", "Start-SORA.ps1", "pyproject.toml", "uv.lock"):
        files[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    routes = (ROOT / "src/sora/api/routes.py").read_text(encoding="utf-8")
    evidence: dict[str, object] = {
        "captured_at": datetime.now(UTC).isoformat(), "contributor": "GPT-6.1 Sol",
        "root": str(ROOT), "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--short"], cwd=ROOT, text=True).splitlines(),
        "settings_version": AppSettings().version,
        "settings_fields": FIELDS,
        "route_string_literals_not_complete_dispatch_matrix": sorted(set(
            re.findall(r'"(/api/v1/[^"?]*)"', routes))),
        "files_sha256": dict(sorted(files.items())),
        "limits": "Source fingerprint, not backup/commit/runtime acceptance. No owner state read.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    record = capture(args.output)
    print(json.dumps({"output": str(args.output), "head": record["head"],
                      "settings_version": record["settings_version"],
                      "source_files": len(record["files_sha256"])}))  # type: ignore[arg-type]
