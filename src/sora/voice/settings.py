"""Local Windows speech preferences, stored with the rest of SORA's settings."""

from pathlib import Path

from pydantic import Field

from sora.contracts.base import StrictModel


class VoiceSettings(StrictModel):
    python_executable: str = Field(default="", max_length=4096)
    stt_model_path: str = Field(default="", max_length=4096)
    tts_model_path: str = Field(default="", max_length=4096)
    voices_path: str = Field(default="", max_length=4096)
    input_device: str = Field(default="", max_length=512)
    output_device: str = Field(default="", max_length=512)
    voice_id: str = Field(default="af_heart", pattern=r"^[a-z][a-z0-9_]{1,63}$")
    recording_limit_seconds: int = Field(default=30, ge=2, le=60)
    speech_speed: float = Field(default=1, ge=0.5, le=2)


def resolve_assets(settings: VoiceSettings, project: Path) -> VoiceSettings:
    """Reuse existing benchmark assets only; never fetch weights on startup."""
    assets = project / ".local/p14-voice-benchmark/models"
    snapshots = list((assets / "stt/models--Systran--faster-whisper-base.en/snapshots").glob("*"))
    values = settings.model_dump()
    defaults = {
        "stt_model_path": snapshots[0] if len(snapshots) == 1 else None,
        "tts_model_path": assets / "tts/kokoro-v1.0.int8.onnx",
        "voices_path": assets / "tts/voices-v1.0.bin",
    }
    for key, candidate in defaults.items():
        if not values[key]:
            if candidate is None or not candidate.exists():
                raise ValueError(
                    f"Set Voice {key.replace('_', ' ')} in Settings; no local asset found."
                )
            values[key] = str(candidate.resolve())
        path = Path(values[key])
        if not path.is_absolute() or str(path).startswith(("\\\\", "//")) or not path.exists():
            raise ValueError(f"Voice {key.replace('_', ' ')} must be an existing local path.")
    if not Path(values["stt_model_path"]).is_dir():
        raise ValueError("Voice STT model must be a local faster-whisper model directory.")
    if not all(Path(values[k]).is_file() for k in ("tts_model_path", "voices_path")):
        raise ValueError("Voice Kokoro model and voice bank must be local files.")
    return VoiceSettings.model_validate(values)
