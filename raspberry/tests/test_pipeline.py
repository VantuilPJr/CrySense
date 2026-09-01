import numpy as np

from crysense.models import Prediction
from crysense.pipeline import TwoStagePipeline


class FakeClassifier:
    ready = True
    load_error = None

    def __init__(self, prediction: Prediction) -> None:
        self.prediction = prediction

    def predict(self, _samples, _sample_rate):
        return self.prediction


class RecordingClassifier(FakeClassifier):
    def __init__(self, prediction: Prediction) -> None:
        super().__init__(prediction)
        self.clips: list[np.ndarray] = []

    def predict(self, samples, _sample_rate):
        self.clips.append(np.asarray(samples).copy())
        return self.prediction


class SequenceClassifier:
    ready = True
    load_error = None

    def __init__(self, predictions: list[Prediction]) -> None:
        self.predictions = predictions
        self.index = 0

    def predict(self, _samples, _sample_rate):
        prediction = self.predictions[min(self.index, len(self.predictions) - 1)]
        self.index += 1
        return prediction


def test_pipeline_preserves_trigger_frames_in_full_clip() -> None:
    trigger = FakeClassifier(Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {}))
    classifier = RecordingClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=6)

    for value in range(1, 6):
        frame = np.full(16_000, value, dtype=np.float32)
        assert pipeline.feed_frame(frame) is None
    event = pipeline.feed_frame(np.full(16_000, 6, dtype=np.float32))
    assert event is not None
    assert event.label == "colic"
    assert event.confidence == 0.90
    assert len(classifier.clips) == 1
    expected = np.concatenate([np.full(16_000, value, dtype=np.float32) for value in range(1, 7)])
    np.testing.assert_array_equal(classifier.clips[0], expected)


def test_pipeline_uses_exact_sample_window_for_irregular_blocks() -> None:
    trigger = FakeClassifier(Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {}))
    classifier = RecordingClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(
        trigger,
        classifier,
        confirmation_window=2,
        confirmation_required=2,
        capture_seconds=2,
    )

    assert pipeline.feed_frame(np.full(5, 1, dtype=np.float32), sample_rate=4) is None
    event = pipeline.feed_frame(np.full(5, 2, dtype=np.float32), sample_rate=4)

    assert event is not None
    np.testing.assert_array_equal(
        classifier.clips[0],
        np.asarray([1, 1, 1, 2, 2, 2, 2, 2], dtype=np.float32),
    )


def test_pipeline_waits_for_future_audio_without_losing_warm_preroll() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    noise = Prediction("noise", 0.98, {"cry": 0.02, "noise": 0.98}, {})
    trigger = SequenceClassifier([noise] * 6 + [cry] * 4)
    classifier = RecordingClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=6)

    for value in range(1, 10):
        assert pipeline.feed_frame(np.full(16_000, value, dtype=np.float32)) is None
    event = pipeline.feed_frame(np.full(16_000, 10, dtype=np.float32))

    assert event is not None
    expected = np.concatenate([np.full(16_000, value, dtype=np.float32) for value in range(5, 11)])
    np.testing.assert_array_equal(classifier.clips[0], expected)


def test_pipeline_emits_once_until_three_quiet_frames_rearm_it() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    noise = Prediction("noise", 0.98, {"cry": 0.02, "noise": 0.98}, {})
    trigger = SequenceClassifier([cry] * 9 + [noise] * 3 + [cry] * 6)
    classifier = RecordingClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=3)
    frame = np.zeros(16_000, dtype=np.float32)
    events = [pipeline.feed_frame(frame) for _ in range(18)]

    assert len([event for event in events if event is not None]) == 2
    assert len(classifier.clips) == 2
