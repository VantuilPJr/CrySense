import wave
from io import BytesIO
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from crysense.app import create_app
from crysense.settings import Settings


class ProbabilityModel:
    def __init__(self, classes: tuple[str, ...], probabilities: tuple[float, ...]) -> None:
        self.classes_ = np.asarray(classes)
        self.probabilities = np.asarray([probabilities], dtype=np.float32)

    def predict_proba(self, _features):
        return self.probabilities


def wav_payload(seconds: float = 6.0, sample_rate: int = 16_000) -> bytes:
    samples = (np.sin(np.linspace(0, 160, int(seconds * sample_rate))) * 4_000).astype("<i2")
    output = BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())
    return output.getvalue()


def test_dashboard_and_status_work_without_peripherals(tmp_path: Path) -> None:
    settings = Settings(
        home=tmp_path,
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        trigger_model_path=tmp_path / "models" / "trigger.joblib",
        type_model_path=tmp_path / "models" / "type.joblib",
        host="127.0.0.1",
        port=8080,
        enable_audio=False,
        enable_camera=False,
        enable_sensor=False,
        enable_tft=False,
        audio_input_device=None,
        audio_output_device=None,
        audio_input_channels=1,
        audio_input_channel=0,
        audio_output_channels=2,
        camera_index=0,
        camera_device=None,
        camera_width=640,
        camera_height=480,
        camera_fps=15,
        camera_rotation=0,
        trigger_threshold=0.80,
        type_threshold=0.75,
        type_margin=0.20,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 200
        health = client.get("/api/health")
        assert health.json() == {"ok": True, "trigger_ready": False, "type_ready": False}
        assert client.get("/api/status").status_code == 200


def test_relative_env_paths_are_inside_project_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYSENSE_HOME", str(tmp_path))
    monkeypatch.setenv("CRYSENSE_TRIGGER_MODEL", "models/trigger.joblib")
    monkeypatch.setenv("CRYSENSE_TYPE_MODEL", "models/type.joblib")
    settings = Settings.from_env()
    assert settings.data_dir == tmp_path / "data"
    assert settings.trigger_model_path == tmp_path / "models" / "trigger.joblib"
    assert settings.type_model_path == tmp_path / "models" / "type.joblib"


def test_uploaded_wav_uses_both_audio_models_and_vision_reports(tmp_path: Path) -> None:
    settings = Settings(
        home=tmp_path,
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        trigger_model_path=tmp_path / "models" / "trigger.joblib",
        type_model_path=tmp_path / "models" / "type.joblib",
        host="127.0.0.1",
        port=8080,
        enable_audio=False,
        enable_camera=False,
        enable_sensor=False,
        enable_tft=False,
        audio_input_device=None,
        audio_output_device=None,
        audio_input_channels=1,
        audio_input_channel=0,
        audio_output_channels=2,
        camera_index=0,
        camera_device=None,
        camera_width=640,
        camera_height=480,
        camera_fps=15,
        camera_rotation=0,
        trigger_threshold=0.80,
        type_threshold=0.75,
        type_margin=0.20,
    )
    with TestClient(create_app(settings)) as client:
        client.app.state.pipeline.trigger.model = ProbabilityModel(("cry", "noise"), (0.93, 0.07))
        client.app.state.pipeline.type_classifier.model = ProbabilityModel(("colic", "hunger"), (0.18, 0.82))
        response = client.post("/api/audio/analyze", files={"audio": ("demonstração.wav", wav_payload(), "audio/wav")})
        assert response.status_code == 200
        result = response.json()
        assert result["trigger"]["label"] == "cry"
        assert result["classification"]["label"] == "hunger"
        assert client.get("/api/events").json()["events"][0]["label"] == "hunger"

        report = client.post(
            "/api/vision/report",
            json={
                "state": "monitoring",
                "alert": True,
                "label": "escape_risk",
                "confidence": 0.88,
                "detail": "Bebê perto da saída",
                "detections": [{"label": "person", "confidence": 0.91, "box": [0.1, 0.2, 0.6, 0.9]}],
            },
        )
        assert report.status_code == 200
        assert client.get("/api/status").json()["vision"]["alert"] is True
        assert client.get("/api/status").json()["vision"]["detections"][0]["label"] == "person"
        assert client.get("/api/vision/events").json()["events"][0]["label"] == "escape_risk"

        saved_zone = client.put("/api/vision/config", json={"risk_zone": [0.1, 0.0, 0.9, 0.28]})
        assert saved_zone.status_code == 200
        assert saved_zone.json()["risk_zone"] == [0.1, 0.0, 0.9, 0.28]
        assert client.get("/api/vision/config").json()["risk_zone"] == [0.1, 0.0, 0.9, 0.28]

        cleared_zone = client.put("/api/vision/config", json={"risk_zone": None})
        assert cleared_zone.status_code == 200
        assert client.get("/api/vision/config").json()["risk_zone"] is None
