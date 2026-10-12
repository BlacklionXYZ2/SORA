"""Load all required identity files into a deterministic revision bundle."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import Field

from sora.contracts.base import StrictModel

IDENTITY_FILES = ("persona.md", "behaviour.md", "speech_style.md", "values.md", "embodiment.md")
# Who SORA is, written by the owner (identity/character.template.md shows the structure). Loaded
# first when present. Like every identity file it is read-only for SORA: none of her tools write
# identity/. Her goals, which she does change, live in Core's database (sora.runtime.goals).
CHARACTER_FILE = "character.md"


class IdentityBundle(StrictModel):
    content_hash: str = Field(min_length=64, max_length=64)
    files: dict[str, str]


def load_identity(directory: Path) -> IdentityBundle:
    files: dict[str, str] = {}
    digest = hashlib.sha256()
    character = directory / CHARACTER_FILE
    names = ((CHARACTER_FILE,) if character.is_file() else ()) + IDENTITY_FILES
    for name in names:
        path = directory / name
        if not path.is_file():
            raise FileNotFoundError(f"required identity file is missing: {path}")
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"required identity file is empty: {path}")
        files[name] = content
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(content.encode())
        digest.update(b"\0")
    return IdentityBundle(content_hash=digest.hexdigest(), files=files)
