"""Which avatar SORA wears: Alice by default, Seed-san when her file is missing."""

from __future__ import annotations

from pathlib import Path

from sora.embodiment.avatar_settings import DEFAULT_AVATAR, AvatarSettings, resolve_avatar
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit


def test_alice_is_the_default_and_seed_san_the_fallback(tmp_path: Path) -> None:
    assert AppSettings().avatar.vrm_path == DEFAULT_AVATAR == ".local/avatars/Alice.vrm"
    assert resolve_avatar(AvatarSettings(), tmp_path) is None  # file missing: Seed-san
    alice = tmp_path / ".local" / "avatars" / "Alice.vrm"
    alice.parent.mkdir(parents=True)
    alice.write_bytes(b"glTF")
    assert resolve_avatar(AvatarSettings(), tmp_path) == alice
    assert resolve_avatar(AvatarSettings(vrm_path=""), tmp_path) is None  # blank: Seed-san
    other = tmp_path / "other.vrm"
    other.write_bytes(b"glTF")
    assert resolve_avatar(AvatarSettings(vrm_path=str(other)), tmp_path) == other
    (tmp_path / "notes.txt").write_text("x")
    assert resolve_avatar(AvatarSettings(vrm_path=str(tmp_path / "notes.txt")), tmp_path) is None


def test_settings_saves_a_blank_or_other_avatar_for_the_next_start(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    field = next(f for f in controller.projection()["fields"] if f["key"] == "avatar.vrm_path")
    assert (field["category"], field["type"], field["tier"]) == (
        "Appearance", "path-file", "next_boot")
    for value in ("", str(tmp_path / "other.vrm")):
        controller.save(SettingsEdit(
            version=10, expected_revision=controller.saved.revision,
            changes={"avatar.vrm_path": value},
        ))
        assert controller.saved.avatar.vrm_path == value
        assert controller.boot.avatar.vrm_path == DEFAULT_AVATAR  # applied when SORA restarts
        assert controller.projection()["restart_required"]
