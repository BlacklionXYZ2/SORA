"""identity/character.md: written by the owner, optional, loaded before the policy files."""

from __future__ import annotations

import shutil
from pathlib import Path

from sora.identity.loader import CHARACTER_FILE, IDENTITY_FILES, load_identity

ROOT = Path(__file__).resolve().parents[2]


def test_character_file_is_optional_and_loaded_first(tmp_path: Path) -> None:
    for name in IDENTITY_FILES:
        shutil.copy(ROOT / "identity" / name, tmp_path / name)
    shutil.copy(ROOT / "identity/character.template.md", tmp_path / "character.template.md")
    without = load_identity(tmp_path)
    assert list(without.files) == list(IDENTITY_FILES)  # the template is never loaded
    (tmp_path / CHARACTER_FILE).write_text("# Character\n\nShe is curious and dry-witted.\n",
                                           encoding="utf-8")
    with_character = load_identity(tmp_path)
    assert list(with_character.files)[0] == CHARACTER_FILE
    assert "dry-witted" in with_character.files[CHARACTER_FILE]
    assert with_character.content_hash != without.content_hash  # a new identity revision
