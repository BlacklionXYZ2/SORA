"""Vision detail levels set llama.cpp's image arguments; hand edits make the level custom."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sora.providers.llama_server import LlamaOptions, llama_arguments
from sora.providers.vision_detail import VISION_PRESETS, expand_choice
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit


def test_new_settings_use_medium_and_pass_the_image_budget_to_llama() -> None:
    options = LlamaOptions(model_path=Path("C:/m.gguf"), mmproj_path=Path("C:/p.gguf"))
    assert options.vision_detail == "medium"
    assert (options.image_max_tokens, options.ubatch_size, options.context_size) == (
        1024, 1024, 12288,
    )
    argv = llama_arguments(options)
    assert argv[argv.index("--image-max-tokens") + 1] == "1024"
    assert argv[argv.index("--ubatch-size") + 1] == "1024"


@pytest.mark.parametrize("saved,expected", [
    # Untouched old defaults move to the default level.
    ({"ubatch_size": 512, "context_size": 8192}, ("medium", 1024, 1024, 12288)),
    ({}, ("medium", 1024, 1024, 12288)),
    # Hand-tuned values are kept; the budget fits the owner's physical batch.
    ({"ubatch_size": 512, "context_size": 32768}, ("custom", 512, 512, 32768)),
    ({"ubatch_size": 2048, "context_size": 32768}, ("custom", 1024, 2048, 32768)),
])
def test_settings_saved_before_vision_detail_load_safely(
    saved: dict[str, int], expected: tuple[object, ...],
) -> None:
    options = LlamaOptions.model_validate(saved)
    assert (options.vision_detail, options.image_max_tokens, options.ubatch_size,
            options.context_size) == expected


def test_arguments_that_differ_from_the_level_make_it_custom() -> None:
    options = LlamaOptions.model_validate({
        "vision_detail": "high", "image_max_tokens": 2048, "ubatch_size": 2048,
        "context_size": 32768,
    })
    assert options.vision_detail == "custom"
    with pytest.raises(ValidationError, match="at least the image token budget"):
        LlamaOptions.model_validate({"image_max_tokens": 2048, "ubatch_size": 1024})


def test_choosing_a_level_writes_its_arguments_and_editing_one_makes_it_custom() -> None:
    high = expand_choice({"llama.vision_detail": "high"}, batch_size=1024)
    assert high == {"llama.vision_detail": "high", "llama.image_max_tokens": 2048,
                    "llama.ubatch_size": 2048, "llama.context_size": 16384,
                    "llama.batch_size": 2048}
    assert expand_choice({"llama.context_size": 20000}, batch_size=2048) == {
        "llama.context_size": 20000, "llama.vision_detail": "custom",
    }
    assert expand_choice({"perception.paused": True}, batch_size=2048) == {
        "perception.paused": True,
    }
    assert set(VISION_PRESETS) == {"low", "medium", "high"}


def test_settings_save_applies_levels_and_custom(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())

    def save(**changes: object) -> None:
        controller.save(SettingsEdit(
            version=10, expected_revision=controller.saved.revision, changes=changes,
        ))

    save(**{"llama.vision_detail": "high"})
    llama = controller.saved.llama
    assert (llama.vision_detail, llama.image_max_tokens, llama.context_size) == (
        "high", 2048, 16384,
    )
    save(**{"llama.image_max_tokens": 1536})
    assert controller.saved.llama.vision_detail == "custom"
    save(**{"llama.vision_detail": "low"})
    llama = controller.saved.llama
    assert (llama.vision_detail, llama.image_max_tokens, llama.ubatch_size) == ("low", 280, 512)
    field = next(item for item in controller.projection()["fields"]
                 if item["key"] == "llama.vision_detail")
    assert field["category"] == "Vision" and field["tier"] == "model_reload"
    assert field["choices"] == ["low", "medium", "high", "custom"]
    assert "increases response times and context usage" in field["help"]
