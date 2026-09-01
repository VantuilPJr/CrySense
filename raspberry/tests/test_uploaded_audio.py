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


class SequenceClassifier:
    ready = True
    seconds = 1.0

    def __init__(self, predictions: list[Prediction]) -> None:
        self.predictions = predictions
        self.calls = 0

    def predict(self, _samples, _sample_rate):
        prediction = self.predictions[min(self.calls, len(self.predictions) - 1)]
        self.calls += 1
        return prediction


class RecordingTypeClassifier:
    ready = True
    seconds = 6.0

    def __init__(self) -> None:
        self.clips: list[np.ndarray] = []

    def predict(self, samples, _sample_rate):
        self.clips.append(np.asarray(samples).copy())
        return Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {})


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


def _prediction(cry_probability: float) -> Prediction:
    scores = {"cry": cry_probability, "noise": 1.0 - cry_probability}
    label = "cry" if cry_probability >= 0.5 else "noise"
    return Prediction(label, max(scores.values()), scores, {})


def test_upload_requires_three_positive_windows_before_calling_type_model() -> None:
    trigger = SequenceClassifier(
        [_prediction(0.95), _prediction(0.10), _prediction(0.92), _prediction(0.15), _prediction(0.12)]
    )
    type_classifier = RecordingTypeClassifier()

    result, event = analyze_uploaded_wav(
        _windowed_wav(5),
        "duas-confirmacoes.wav",
        trigger,
        type_classifier,
        trigger_threshold=0.80,
        type_threshold=0.68,
        type_margin=0.20,
    )

    assert result["trigger_confirmation"]["positive_windows"] == 2
    assert result["trigger_confirmation"]["confirmed"] is False
    assert event is None
    assert type_classifier.clips == []


def test_upload_selects_six_seconds_around_confirmed_window() -> None:
    trigger = SequenceClassifier(
        [_prediction(0.10)] * 4
        + [_prediction(0.91), _prediction(0.93), _prediction(0.95)]
        + [_prediction(0.10)]
    )
    type_classifier = RecordingTypeClassifier()

    result, event = analyze_uploaded_wav(
        _windowed_wav(8),
        "choro-tardio.wav",
        trigger,
        type_classifier,
        trigger_threshold=0.80,
        type_threshold=0.68,
        type_margin=0.20,
    )

    assert event is not None
    assert result["selected_clip"] == {"start_seconds": 1.0, "end_seconds": 7.0}
    assert len(type_classifier.clips) == 1
    assert type_classifier.clips[0].size == 600
    assert type_classifier.clips[0][0] == pytest.approx(1_000 / 32_768)
    assert type_classifier.clips[0][-1] == pytest.approx(6_000 / 32_768)


def test_upload_early_confirmation_keeps_the_beginning_of_a_long_file() -> None:
    trigger = SequenceClassifier(
        [_prediction(0.95)] * 3 + [_prediction(0.10)] * 5
    )
    type_classifier = RecordingTypeClassifier()

    result, event = analyze_uploaded_wav(
        _windowed_wav(8),
        "choro-no-inicio.wav",
        trigger,
        type_classifier,
        trigger_threshold=0.80,
        type_threshold=0.68,
        type_margin=0.20,
    )

    assert event is not None
    assert result["selected_clip"] == {"start_seconds": 0.0, "end_seconds": 6.0}
    assert type_classifier.clips[0][0] == pytest.approx(0.0)
    assert type_classifier.clips[0][-1] == pytest.approx(5_000 / 32_768)


def test_training_colic_file_crosses_both_models_and_generates_event() -> None:
    project_root = Path(__file__).resolve().parents[1]
    audio_path = _dataset_file(project_root)
    assert audio_path.is_file(), f"arquivo de regressão ausente: {audio_path}"

    trigger = AudioClassifier(project_root / "models" / "trigger.joblib", ("cry", "noise"), seconds=1.0)
    type_classifier = AudioClassifier(
        project_root / "models" / "type.joblib",
        ("colic", "hunger"),
        seconds=6.0,
    )
    trigger.load()
    type_classifier.load()

    result, event = analyze_uploaded_wav(
        audio_path.read_bytes(),
        audio_path.name,
        trigger,
        type_classifier,
        trigger_threshold=0.80,
        type_threshold=0.68,
        type_margin=0.20,
    )

    assert result["trigger_confirmation"]["confirmed"] is True
    assert result["trigger_confirmation"]["positive_windows"] >= 3
    assert result["trigger_confirmation"]["analyzed_windows"] == 6
    assert result["trigger_windows"][0]["scores"]["cry"] == pytest.approx(0.650317, abs=1e-5)
    assert result["classification"]["label"] == "colic"
    assert result["classification"]["confidence"] >= 0.68
    assert result["alert_triggered"] is True
    assert event is not None
    assert event.label == "colic"
