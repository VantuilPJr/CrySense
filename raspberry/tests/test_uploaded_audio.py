import wave
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from crysense.models import AudioClassifier, Prediction
from crysense.uploaded_audio import analyze_uploaded_wav

pytestmark = pytest.mark.filterwarnings(
    "ignore:Setting the shape on a NumPy array has been deprecated:DeprecationWarning"
)


def _dataset_file(project_root: Path) -> Path:
    relative = Path("datasetIA2") / "colic" / "colicaRevisado7.wav"
    local = project_root / relative
    return local if local.is_file() else project_root.parent / relative


class RecordingTypeClassifier:
    ready = True
    seconds = 6.0

    def __init__(self, prediction: Prediction | None = None) -> None:
        self.prediction = prediction or Prediction(
            "colic",
            0.90,
            {"colic": 0.90, "hunger": 0.10},
            {},
        )
        self.clips: list[np.ndarray] = []

    def predict(self, samples, _sample_rate):
        self.clips.append(np.asarray(samples).copy())
        return self.prediction


def _windowed_wav(seconds: int, sample_rate: int = 100) -> bytes:
    samples = np.concatenate(
        [np.full(sample_rate, second * 1_000, dtype="<i2") for second in range(seconds)]
    )
    output = BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())
    return output.getvalue()


def test_upload_goes_directly_to_type_model_once() -> None:
    type_classifier = RecordingTypeClassifier()

    result, event = analyze_uploaded_wav(
        _windowed_wav(6),
        "choro-conhecido.wav",
        type_classifier,
        type_threshold=0.68,
        type_margin=0.20,
    )

    assert len(type_classifier.clips) == 1
    assert result["analysis_mode"] == "uploaded_known_cry"
    assert result["ia1_bypassed"] is True
    assert "trigger" not in result
    assert "trigger_confirmation" not in result
    assert result["classification"]["label"] == "colic"
    assert result["alert_triggered"] is True
    assert event is not None
    assert event.trigger_confidence == 1.0


def test_upload_rejects_audio_shorter_than_three_seconds() -> None:
    type_classifier = RecordingTypeClassifier()

    with pytest.raises(ValueError, match="pelo menos 3 segundos"):
        analyze_uploaded_wav(
            _windowed_wav(2),
            "curto.wav",
            type_classifier,
            type_threshold=0.68,
            type_margin=0.20,
        )

    assert type_classifier.clips == []


def test_upload_reports_padding_for_clip_shorter_than_model_window() -> None:
    type_classifier = RecordingTypeClassifier()

    result, event = analyze_uploaded_wav(
        _windowed_wav(5),
        "cinco-segundos.wav",
        type_classifier,
        type_threshold=0.68,
        type_margin=0.20,
    )

    assert event is not None
    assert type_classifier.clips[0].size == 500
    assert result["selected_clip"] == {
        "start_seconds": 0.0,
        "end_seconds": 5.0,
        "model_window_seconds": 6.0,
        "padded_seconds": 1.0,
        "truncated": False,
    }


def test_upload_uses_only_first_six_seconds_of_long_file() -> None:
    type_classifier = RecordingTypeClassifier()

    result, event = analyze_uploaded_wav(
        _windowed_wav(8),
        "choro-longo.wav",
        type_classifier,
        type_threshold=0.68,
        type_margin=0.20,
    )

    assert event is not None
    assert type_classifier.clips[0].size == 600
    assert type_classifier.clips[0][0] == pytest.approx(0.0)
    assert type_classifier.clips[0][-1] == pytest.approx(5_000 / 32_768)
    assert result["selected_clip"]["end_seconds"] == 6.0
    assert result["selected_clip"]["truncated"] is True


@pytest.mark.parametrize(
    ("prediction", "type_threshold", "type_margin"),
    [
        (Prediction("colic", 0.65, {"colic": 0.65, "hunger": 0.35}, {}), 0.68, 0.20),
        (Prediction("colic", 0.55, {"colic": 0.55, "hunger": 0.45}, {}), 0.50, 0.20),
    ],
)
def test_upload_does_not_alert_below_confidence_or_margin(
    prediction: Prediction,
    type_threshold: float,
    type_margin: float,
) -> None:
    result, event = analyze_uploaded_wav(
        _windowed_wav(6),
        "inconclusivo.wav",
        RecordingTypeClassifier(prediction),
        type_threshold=type_threshold,
        type_margin=type_margin,
    )

    assert result["classification"]["label"] == "colic"
    assert result["alert_triggered"] is False
    assert event is None


def test_training_colic_file_goes_directly_to_ia2_and_generates_event() -> None:
    project_root = Path(__file__).resolve().parents[1]
    audio_path = _dataset_file(project_root)
    assert audio_path.is_file(), f"arquivo de regressão ausente: {audio_path}"

    type_classifier = AudioClassifier(
        project_root / "models" / "type.joblib",
        ("colic", "hunger"),
        seconds=6.0,
    )
    type_classifier.load()

    result, event = analyze_uploaded_wav(
        audio_path.read_bytes(),
        audio_path.name,
        type_classifier,
        type_threshold=0.68,
        type_margin=0.20,
    )

    assert result["analysis_mode"] == "uploaded_known_cry"
    assert result["ia1_bypassed"] is True
    assert result["selected_clip"]["padded_seconds"] == pytest.approx(0.027, abs=0.001)
    assert result["classification"]["label"] == "colic"
    assert result["classification"]["confidence"] == pytest.approx(0.6930289, abs=1e-5)
    assert result["alert_triggered"] is True
    assert event is not None
    assert event.label == "colic"
    assert event.trigger_confidence == 1.0
