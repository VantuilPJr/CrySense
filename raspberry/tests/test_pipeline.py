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


def test_pipeline_requires_confirmation_and_full_clip() -> None:
    trigger = FakeClassifier(Prediction("cry", 0.95, {"cry": 0.95, "noise": 0.05}, {}))
    classifier = FakeClassifier(Prediction("colic", 0.90, {"colic": 0.90, "hunger": 0.10}, {}))
    pipeline = TwoStagePipeline(trigger, classifier, capture_seconds=6)
    frame = np.zeros(16_000, dtype=np.float32)

    for _ in range(8):
        assert pipeline.feed_frame(frame) is None
    event = pipeline.feed_frame(frame)
    assert event is not None
    assert event.label == "colic"
    assert event.confidence == 0.90
