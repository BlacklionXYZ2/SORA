"""Vision detail levels: one owner-facing choice that sets llama.cpp's image arguments.

llama.cpp scales every image to fit --image-max-tokens before the vision encoder sees it, so the
token budget, not the size of the captured image, decides how much SORA can read. Without the
flag Gemma 4 images land at about 1200x480 pixels (about 250 tokens), and small screen text
becomes unreadable or invented. An image must fit one physical batch, so --ubatch-size has to be
at least the budget, and the context must hold the desktop image, a closer window image and the
conversation.

Changing any of these arguments by hand turns the level into "custom".
"""

from __future__ import annotations

from typing import Any, Literal

VisionDetail = Literal["low", "medium", "high", "custom"]

# image_max_tokens, ubatch_size, context_size. About 2,304 source pixels per image token.
VISION_PRESETS: dict[str, dict[str, int]] = {
    "low": {"image_max_tokens": 280, "ubatch_size": 512, "context_size": 8192},
    "medium": {"image_max_tokens": 1024, "ubatch_size": 1024, "context_size": 12288},
    "high": {"image_max_tokens": 2048, "ubatch_size": 2048, "context_size": 16384},
}
VISION_ARGUMENTS = tuple(VISION_PRESETS["low"])
DEFAULT_VISION_DETAIL: VisionDetail = "medium"
# Settings saved before vision detail existed used these values when the owner never changed them.
LEGACY_DEFAULTS = {"ubatch_size": 512, "context_size": 8192}


def matches_preset(level: str, values: dict[str, Any]) -> bool:
    preset = VISION_PRESETS.get(level)
    return preset is not None and all(values.get(name) == value for name, value in preset.items())


def fill_missing(data: dict[str, Any]) -> dict[str, Any]:
    """Give llama options saved before vision detail existed a level and a budget.

    Untouched old defaults move to the default level. Hand-tuned values are kept and become
    custom, with a budget the owner's physical batch can hold.
    """
    if "image_max_tokens" in data:
        return data
    result = dict(data)
    if "vision_detail" not in result and all(
        result.get(name, value) == value for name, value in LEGACY_DEFAULTS.items()
    ):
        result["vision_detail"] = DEFAULT_VISION_DETAIL
        result.update(VISION_PRESETS[DEFAULT_VISION_DETAIL])
        return result
    level = result.get("vision_detail", "custom")
    if level in VISION_PRESETS:
        result.update(VISION_PRESETS[level])
        return result
    result["vision_detail"] = "custom"
    ubatch = result.get("ubatch_size")
    budget = VISION_PRESETS[DEFAULT_VISION_DETAIL]["image_max_tokens"]
    result["image_max_tokens"] = min(budget, ubatch) if isinstance(ubatch, int) else budget
    return result


def expand_choice(changes: dict[str, Any], batch_size: int) -> dict[str, Any]:
    """Turn an edit into stored values.

    Choosing a level writes its three arguments, and raises the logical batch if it would
    otherwise be smaller than the physical batch. Editing an argument without choosing a level
    makes the level custom.
    """
    result = dict(changes)
    level = result.get("llama.vision_detail")
    if level in VISION_PRESETS:
        for name, value in VISION_PRESETS[level].items():
            result["llama." + name] = value
        wanted = result.get("llama.batch_size", batch_size)
        if isinstance(wanted, int) and wanted < result["llama.ubatch_size"]:
            result["llama.batch_size"] = result["llama.ubatch_size"]
    elif level is None and any("llama." + name in result for name in VISION_ARGUMENTS):
        result["llama.vision_detail"] = "custom"
    return result
