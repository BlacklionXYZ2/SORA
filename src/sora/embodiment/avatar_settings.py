"""Which VRM avatar SORA wears (Settings → Appearance), applied when SORA next starts.

The default is **Alice** (owner's choice, 2026-10-11): "Alice", Zenless Zone Zero, original
model by miHoYo, VRM by Niko on VRoid Hub. Her licence allows avatar use by anyone with credit,
and forbids modification, redistribution, commercial use, and sexual or violent expression. So
the file lives in ``.local/avatars/`` (outside git), is never edited or converted (Unity loads
the VRM 0.x file and migrates it in memory), and isn't shipped. Where the file is missing, the
built-in Seed-san is used.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from sora.contracts.base import StrictModel

DEFAULT_AVATAR = ".local/avatars/Alice.vrm"
CREDIT = "Alice (Zenless Zone Zero): original model by miHoYo; VRM by Niko on VRoid Hub"


class AvatarSettings(StrictModel):
    # Relative paths are inside the SORA folder. Blank: always the built-in Seed-san.
    vrm_path: str = Field(default=DEFAULT_AVATAR, max_length=4096)


def resolve_avatar(settings: AvatarSettings, project: Path) -> Path | None:
    """The avatar file to load, or None for the built-in Seed-san (blank or missing file)."""
    raw = settings.vrm_path.strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = project / path
    return path if path.is_file() and path.suffix.lower() == ".vrm" else None
