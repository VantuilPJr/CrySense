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


class RecordingSequenceClassifier(SequenceClassifier):
    def __init__(self, predictions: list[Prediction]) -> None:
        super().__init__(predictions)
        self.clips: list[np.ndarray] = []

    def predict(self, samples, sample_rate):
        self.clips.append(np.asarray(samples).copy())
        return super().predict(samples, sample_rate)


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
        np.asarray([1, 1, 1, 1, 1, 2, 2, 2], dtype=np.float32),
    )


def test_pipeline_starts_type_clip_at_first_positive_trigger_frame() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    noise = Prediction("noise", 0.98, {"cry": 0.02, "noise": 0.98}, {})
    trigger = SequenceClassifier([noise] * 2 + [cry] * 6)
    classifier = RecordingClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=6)

    for value in range(1, 8):
        assert pipeline.feed_frame(np.full(16_000, value, dtype=np.float32)) is None
    event = pipeline.feed_frame(np.full(16_000, 8, dtype=np.float32))

    assert event is not None
    expected = np.concatenate([np.full(16_000, value, dtype=np.float32) for value in range(3, 9)])
    np.testing.assert_array_equal(classifier.clips[0], expected)


def test_pipeline_preserves_weak_cry_onset_before_threshold_confirmation() -> None:
    weak_cry = Prediction("cry", 0.65, {"cry": 0.65, "noise": 0.35}, {})
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    trigger = SequenceClassifier([weak_cry, cry, cry, weak_cry, cry, cry])
    classifier = RecordingClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=6)

    for value in range(1, 6):
        assert pipeline.feed_frame(np.full(16_000, value, dtype=np.float32)) is None
    event = pipeline.feed_frame(np.full(16_000, 6, dtype=np.float32))

    assert event is not None
    expected = np.concatenate([np.full(16_000, value, dtype=np.float32) for value in range(1, 7)])
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


def test_status_exposes_confirmation_and_capture_progress() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    trigger = FakeClassifier(cry)
    classifier = RecordingClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=6)
    frame = np.zeros(16_000, dtype=np.float32)

    pipeline.feed_frame(frame)
    status = pipeline.status()
    assert status["confirmation"] == {
        "positive_windows": 1,
        "required_windows": 3,
        "window_size": 5,
        "evaluated_windows": 1,
    }

    pipeline.feed_frame(frame)
    pipeline.feed_frame(frame)
    status = pipeline.status()
    assert status["phase"] == "capturing_type_audio"
    assert status["capture_progress"] == 0.5
    assert status["episode_active"] is True
    assert status["alert_latched"] is False


def test_inconclusive_type_result_retries_with_new_audio_and_then_alerts() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    trigger = FakeClassifier(cry)
    classifier = SequenceClassifier(
        [
            Prediction("colic", 0.66, {"colic": 0.66, "hunger": 0.34}, {}),
            Prediction("colic", 0.91, {"colic": 0.91, "hunger": 0.09}, {}),
        ]
    )
    events: list = []
    pipeline = TwoStagePipeline(
        trigger,
        classifier,
        capture_seconds=3,
        on_event=events.append,
    )

    for value in range(1, 4):
        assert pipeline.feed_frame(np.full(16_000, value, dtype=np.float32)) is None

    first_status = pipeline.status()
    assert first_status["last_type_decision"]["state"] == "inconclusive"
    assert first_status["last_type_decision"]["reason"] == "low_confidence"
    assert first_status["last_type_decision"]["attempt"] == 1
    assert first_status["last_type_decision"]["retry_scheduled"] is True
    assert first_status["alert_latched"] is False
    assert first_status["armed"] is True

    assert pipeline.feed_frame(np.full(16_000, 4, dtype=np.float32)) is None
    assert pipeline.feed_frame(np.full(16_000, 5, dtype=np.float32)) is None
    event = pipeline.feed_frame(np.full(16_000, 6, dtype=np.float32))

    assert event is not None
    assert event.label == "colic"
    assert len(events) == 1
    final_status = pipeline.status()
    assert final_status["last_type_decision"]["state"] == "accepted"
    assert final_status["last_type_decision"]["attempt"] == 2
    assert final_status["last_type_decision"]["retry_scheduled"] is False
    assert final_status["alert_latched"] is True


def test_retry_waits_for_a_fresh_confirmation() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    trigger = FakeClassifier(cry)
    classifier = RecordingClassifier(Prediction("colic", 0.66, {"colic": 0.66, "hunger": 0.34}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=3)
    frame = np.zeros(16_000, dtype=np.float32)

    for _ in range(3):
        pipeline.feed_frame(frame)
    assert len(classifier.clips) == 1

    pipeline.feed_frame(frame)
    pipeline.feed_frame(frame)
    assert len(classifier.clips) == 1
    assert pipeline.status()["confirmation"]["positive_windows"] == 2

    pipeline.feed_frame(frame)
    assert len(classifier.clips) == 2


def test_three_quiet_frames_cancel_an_inconclusive_episode() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    noise = Prediction("noise", 0.98, {"cry": 0.02, "noise": 0.98}, {})
    trigger = SequenceClassifier([cry] * 3 + [noise] * 3 + [cry] * 3)
    classifier = SequenceClassifier(
        [
            Prediction("colic", 0.66, {"colic": 0.66, "hunger": 0.34}, {}),
            Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}),
        ]
    )
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=3)
    frame = np.zeros(16_000, dtype=np.float32)

    for _ in range(6):
        assert pipeline.feed_frame(frame) is None
    status = pipeline.status()
    assert status["episode_active"] is False
    assert status["last_type_decision"]["retry_scheduled"] is False

    event = None
    for _ in range(3):
        event = pipeline.feed_frame(frame)
    assert event is not None
    assert pipeline.status()["last_type_decision"]["attempt"] == 1


def test_default_retry_classifies_six_fresh_seconds() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    trigger = FakeClassifier(cry)
    classifier = RecordingSequenceClassifier(
        [
            Prediction("colic", 0.66, {"colic": 0.66, "hunger": 0.34}, {}),
            Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}),
        ]
    )
    pipeline = TwoStagePipeline(trigger, classifier)

    events = []
    for value in range(1, 13):
        events.append(pipeline.feed_frame(np.full(16_000, value, dtype=np.float32)))

    assert events[5] is None
    assert events[11] is not None
    assert len(classifier.clips) == 2
    first_expected = np.concatenate(
        [np.full(16_000, value, dtype=np.float32) for value in range(1, 7)]
    )
    retry_expected = np.concatenate(
        [np.full(16_000, value, dtype=np.float32) for value in range(7, 13)]
    )
    np.testing.assert_array_equal(classifier.clips[0], first_expected)
    np.testing.assert_array_equal(classifier.clips[1], retry_expected)


def test_weak_cry_does_not_cancel_an_inconclusive_retry() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    weak_cry = Prediction("cry", 0.65, {"cry": 0.65, "noise": 0.35}, {})
    trigger = SequenceClassifier([cry] * 3 + [weak_cry] * 3 + [cry] * 3)
    classifier = SequenceClassifier(
        [
            Prediction("colic", 0.66, {"colic": 0.66, "hunger": 0.34}, {}),
            Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}),
        ]
    )
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=3)
    frame = np.zeros(16_000, dtype=np.float32)

    for _ in range(6):
        assert pipeline.feed_frame(frame) is None
    assert pipeline.status()["last_type_decision"]["retry_scheduled"] is True

    event = None
    for _ in range(3):
        event = pipeline.feed_frame(frame)
    assert event is not None
    assert pipeline.status()["last_type_decision"]["attempt"] == 2


def test_weak_cry_does_not_rearm_an_accepted_alert() -> None:
    cry = Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {})
    weak_cry = Prediction("cry", 0.65, {"cry": 0.65, "noise": 0.35}, {})
    trigger = SequenceClassifier([cry] * 3 + [weak_cry] * 3 + [cry] * 3)
    classifier = RecordingClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=3)
    frame = np.zeros(16_000, dtype=np.float32)

    events = [pipeline.feed_frame(frame) for _ in range(9)]

    assert len([event for event in events if event is not None]) == 1
    assert len(classifier.clips) == 1
    assert pipeline.status()["alert_latched"] is True
