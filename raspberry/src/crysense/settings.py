from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value in (None, "") else int(value)


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value in (None, "") else float(value)


def _project_path(value: str | Path, home: Path) -> Path:
    """Resolve caminhos relativos do arquivo /etc/crysense.env dentro do projeto."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else home / path


@dataclass(frozen=True)
class Settings:
    home: Path
    data_dir: Path
    models_dir: Path
    trigger_model_path: Path
    type_model_path: Path
    host: str
    port: int
    enable_audio: bool
    enable_camera: bool
    enable_sensor: bool
    enable_tft: bool
    audio_input_device: str | None
    audio_output_device: str | None
    audio_input_channels: int
    audio_input_channel: int
    audio_output_channels: int
    camera_index: int
    camera_device: str | None
    camera_width: int
    camera_height: int
    camera_fps: int
    camera_rotation: float
    trigger_threshold: float
    type_threshold: float
    type_margin: float
    pink_noise_volume: float = 0.10
    vision_token: str = ""
    vision_status_timeout: float = 8.0

    @classmethod
    def from_env(cls) -> Settings:
        home = Path(os.getenv("CRYSENSE_HOME", Path.cwd())).expanduser().resolve()
        models_dir = home / "models"
        return cls(
            home=home,
            data_dir=_project_path(os.getenv("CRYSENSE_DATA_DIR", "data"), home),
            models_dir=models_dir,
            trigger_model_path=_project_path(
                os.getenv("CRYSENSE_TRIGGER_MODEL", str(models_dir / "trigger.joblib")), home
            ),
            type_model_path=_project_path(os.getenv("CRYSENSE_TYPE_MODEL", str(models_dir / "type.joblib")), home),
            host=os.getenv("CRYSENSE_HOST", "0.0.0.0"),
            port=_int("CRYSENSE_PORT", 8080),
            enable_audio=_bool("CRYSENSE_ENABLE_AUDIO", False),
            enable_camera=_bool("CRYSENSE_ENABLE_CAMERA", False),
            enable_sensor=_bool("CRYSENSE_ENABLE_SENSOR", False),
            enable_tft=_bool("CRYSENSE_ENABLE_TFT", False),
            audio_input_device=os.getenv("CRYSENSE_AUDIO_INPUT_DEVICE") or None,
            audio_output_device=os.getenv("CRYSENSE_AUDIO_OUTPUT_DEVICE") or None,
            audio_input_channels=_int("CRYSENSE_AUDIO_INPUT_CHANNELS", 1),
            audio_input_channel=_int("CRYSENSE_AUDIO_INPUT_CHANNEL", 0),
            audio_output_channels=_int("CRYSENSE_AUDIO_OUTPUT_CHANNELS", 2),
            camera_index=_int("CRYSENSE_CAMERA_INDEX", 0),
            camera_device=os.getenv("CRYSENSE_CAMERA_DEVICE") or None,
            camera_width=_int("CRYSENSE_CAMERA_WIDTH", 640),
            camera_height=_int("CRYSENSE_CAMERA_HEIGHT", 480),
            camera_fps=_int("CRYSENSE_CAMERA_FPS", 15),
            camera_rotation=_float("CRYSENSE_CAMERA_ROTATION", 0),
            trigger_threshold=_float("CRYSENSE_TRIGGER_THRESHOLD", 0.80),
            type_threshold=_float("CRYSENSE_TYPE_THRESHOLD", 0.68),
            type_margin=_float("CRYSENSE_TYPE_MARGIN", 0.20),
            pink_noise_volume=_float("CRYSENSE_PINK_NOISE_VOLUME", 0.10),
            vision_token=os.getenv("CRYSENSE_VISION_TOKEN", "").strip(),
            vision_status_timeout=_float("CRYSENSE_VISION_STATUS_TIMEOUT", 8.0),
        )
