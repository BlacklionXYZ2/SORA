"""The motion engine setting and the Motion window's catalogue (2026-10-27)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sora.api import motion_routes
from sora.api.protocol import HttpRequest
from sora.embodiment.motion_catalog import MotionCatalog, load_catalog, load_preview
from sora.embodiment.motion_settings import MotionSettings, resolve_lab
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit


def lab_with(tmp_path: Path, catalog: dict[str, Any]) -> Path:
    lab = tmp_path / "motion-lab"
    (lab / "catalog" / "previews").mkdir(parents=True)
    (lab / "catalog" / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    return lab


CATALOG = {
    "version": 1,
    "recordings": {"outside_limits_share": 0.004, "foot_slide_m_s": 0.079},
    "engines": [
        {"id": "ardy", "name": "ARDY (NVIDIA)", "models": [
            {"version": "Core fp16", "size": "192M", "state": "ready",
             "measures": {"outside_limits_share": 0.0012, "step_latency_ms": 314},
             "preview": "previews/ardy-fp16.json", "files": ["external/denoiser.onnx"]},
        ]},
        {"id": "custom", "name": "Custom trained", "models": [
            {"version": "v4", "size": "0.8M", "parameters": 828979, "state": "experimental",
             "files": ["versions/v4/runs/combined/best.pt"]},
            {"version": "v4", "size": "17.5M", "state": "planned"},
        ]},
    ],
}


def test_the_engine_defaults_to_algorithmic_and_waits_for_reload_motion_model(
    tmp_path: Path,
) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    fields = {f["key"]: f for f in controller.projection()["fields"]
              if f["key"].startswith("motion.")}
    assert set(fields) == {f"motion.{name}" for name in MotionSettings.model_fields}
    # Since 2026-10-27 (the same day) these apply with Reload motion model, not a restart.
    assert all(f["category"] == "Motion" and f["tier"] == "motion_reload"
               for f in fields.values())
    assert fields["motion.engine"]["value"] == "algorithmic"
    assert fields["motion.engine"]["choices"] == ["algorithmic", "ardy", "custom"]
    controller.save(SettingsEdit(version=10, expected_revision=controller.saved.revision,
                                 changes={"motion.engine": "ardy", "motion.ardy_steps": 6}))
    assert (controller.saved.motion.engine, controller.saved.motion.ardy_steps) == ("ardy", 6)
    assert controller.active.motion.engine == "algorithmic"  # until Reload motion model
    assert controller.projection()["motion_reload_required"]
    assert not controller.projection()["restart_required"]


def test_motion_settings_reject_impossible_values() -> None:
    for bad in ({"engine": "dance"}, {"ardy_steps": 1}, {"ardy_steps": 11},
                {"custom_version": "../v4"}, {"custom_size": "big"}):
        with pytest.raises(ValueError):
            MotionSettings.model_validate(bad)


def test_settings_saved_before_motion_existed_load_with_the_default(tmp_path: Path) -> None:
    path = tmp_path / "data" / "sora-settings.json"
    path.parent.mkdir()
    old = AppSettings().model_dump(mode="json")
    del old["motion"]
    path.write_text(json.dumps(old), encoding="utf-8")
    assert AppSettingsController(tmp_path, AppSettings()).saved.motion == MotionSettings()


def test_motion_lab_defaults_to_beside_sora(tmp_path: Path) -> None:
    sora = tmp_path / "SORA"
    assert resolve_lab(MotionSettings(), sora) == tmp_path / "motion-lab"
    assert resolve_lab(MotionSettings(lab_path=str(tmp_path / "x")), sora) == tmp_path / "x"


def test_without_motion_lab_only_the_algorithmic_engine_is_offered(tmp_path: Path) -> None:
    catalog = load_catalog(MotionSettings(), tmp_path / "SORA")
    assert [e.id for e in catalog.engines] == ["algorithmic"]
    assert catalog.engines[0].models[0].state == "ready"
    assert not catalog.lab_found and "not found" in catalog.note


def test_the_catalogue_puts_algorithmic_first_and_marks_vanished_files_missing(
    tmp_path: Path,
) -> None:
    lab = lab_with(tmp_path, CATALOG)
    (lab / "versions/v4/runs/combined").mkdir(parents=True)
    (lab / "versions/v4/runs/combined/best.pt").write_bytes(b"x")
    catalog = load_catalog(MotionSettings(), tmp_path / "SORA")
    assert [e.id for e in catalog.engines] == ["algorithmic", "ardy", "custom"]
    ardy, custom = catalog.engines[1], catalog.engines[2]
    assert ardy.models[0].state == "missing"  # its ONNX file isn't there
    assert [m.state for m in custom.models] == ["experimental", "planned"]
    assert catalog.recordings.foot_slide_m_s == 0.079
    MotionCatalog.model_validate(catalog.model_dump(mode="json"))  # the contract round-trips


def test_an_unreadable_catalogue_says_why_and_keeps_the_algorithmic_engine(tmp_path: Path) -> None:
    lab_with(tmp_path, {"version": 1, "engines": [{"id": "ardy", "name": "x", "models": [
        {"version": "a", "size": "1M", "state": "excellent"}]}]})
    catalog = load_catalog(MotionSettings(), tmp_path / "SORA")
    assert [e.id for e in catalog.engines] == ["algorithmic"]
    assert "couldn't be read" in catalog.note


def test_previews_are_only_read_from_the_catalogue_folder(tmp_path: Path) -> None:
    lab = lab_with(tmp_path, CATALOG)
    clip = {"fps": 10, "joint_names": ["hips"], "joint_parents": [-1], "frames": [[0, 900, 0]]}
    (lab / "catalog/previews/ardy-fp16.json").write_text(json.dumps(clip), encoding="utf-8")
    settings, project = MotionSettings(), tmp_path / "SORA"
    assert load_preview(settings, project, "previews/ardy-fp16.json") == clip
    for bad in ("../catalog.json", "previews/../../x.json", "previews/a b.json", "catalog.json"):
        with pytest.raises(ValueError):
            load_preview(settings, project, bad)
    with pytest.raises(FileNotFoundError):
        load_preview(settings, project, "previews/none.json")


def test_routes_serve_the_catalogue_and_previews(tmp_path: Path) -> None:
    lab_with(tmp_path, CATALOG)
    settings, project = MotionSettings(), tmp_path / "SORA"
    catalog = motion_routes.handle(motion_routes.CATALOG,
                                   HttpRequest("GET", motion_routes.CATALOG, {}, b""),
                                   settings, project)
    assert catalog.status_code == 200
    engines = json.loads(catalog.body)["engines"]
    assert [e["id"] for e in engines] == ["algorithmic", "ardy", "custom"]
    missing = motion_routes.handle(motion_routes.PREVIEW, HttpRequest(
        "GET", f"{motion_routes.PREVIEW}?name=previews/none.json", {}, b""), settings, project)
    bad = motion_routes.handle(motion_routes.PREVIEW, HttpRequest(
        "GET", f"{motion_routes.PREVIEW}?name=../x.json", {}, b""), settings, project)
    assert (missing.status_code, bad.status_code) == (404, 422)
