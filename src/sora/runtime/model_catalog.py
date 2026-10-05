"""Owner-local LM Studio model choices inside an explicitly selected folder."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any


class ModelCatalogError(ValueError):
    """The selected folder or LM Studio catalog cannot supply usable model choices."""


def normalize_model_folder(folder_text: str) -> Path:
    if not folder_text.strip() or len(folder_text) > 4096:
        raise ModelCatalogError("Choose an existing local LM Studio models folder.")
    raw = folder_text.strip().strip('"')
    if raw.startswith(("\\\\", "//")):
        raise ModelCatalogError("Choose a local models folder, not a network path.")
    try:
        folder = Path(raw).expanduser().resolve(strict=False)
    except OSError as exc:
        raise ModelCatalogError("The selected models folder is invalid.") from exc
    if str(folder).startswith(("\\\\", "//")):
        raise ModelCatalogError("Choose a local models folder, not a network path.")
    return folder


def resolve_model_folder(folder_text: str) -> Path:
    folder = normalize_model_folder(folder_text)
    if not folder.is_dir():
        raise ModelCatalogError("The selected models folder does not exist.")
    return folder


async def scan_lm_studio_models(folder_text: str) -> list[dict[str, Any]]:
    """Match LM Studio's indexed LLMs to files under the chosen root; never read weights."""
    folder = resolve_model_folder(folder_text)
    process: asyncio.subprocess.Process | None = None
    try:
        async with asyncio.timeout(12):
            process = await asyncio.create_subprocess_exec(
                "lms", "ls", "--json", stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            stdout, _ = await process.communicate()
    except (OSError, TimeoutError) as exc:
        raise ModelCatalogError("LM Studio CLI is unavailable or did not respond.") from exc
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
    assert process is not None
    if process.returncode != 0 or len(stdout) > 2_000_000:
        raise ModelCatalogError("LM Studio could not list its local models.")
    try:
        catalog = json.loads(stdout)
    except (ValueError, UnicodeError) as exc:
        raise ModelCatalogError("LM Studio returned an invalid model catalog.") from exc
    if not isinstance(catalog, list):
        raise ModelCatalogError("LM Studio returned an invalid model catalog.")
    choices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in catalog[:2000]:
        if not isinstance(record, dict) or record.get("type") != "llm":
            continue
        relative = record.get("path")
        model_key = record.get("modelKey")
        if (
            not isinstance(relative, str) or len(relative) > 4096
            or not isinstance(model_key, str) or not 1 <= len(model_key) <= 200
        ):
            continue
        parts = relative.replace("\\", "/").split("/")
        if not parts or any(part in {"", ".", ".."} or ":" in part for part in parts):
            continue
        if not parts[-1].lower().endswith(".gguf"):
            continue
        candidate = folder.joinpath(*parts)
        try:
            file = candidate.resolve(strict=True)
            file.relative_to(folder)
            if not file.is_file() or model_key in seen:
                continue
            size = file.stat().st_size
        except (OSError, ValueError):
            continue
        seen.add(model_key)
        choices.append({
            "model_key": model_key,
            "display_name": str(record.get("displayName") or file.stem)[:200],
            "relative_path": "/".join(parts),
            "size_bytes": size,
            "vision": record.get("vision") is True,
        })
        if len(choices) >= 300:
            break
    return sorted(choices, key=lambda item: (item["display_name"].casefold(), item["model_key"]))
