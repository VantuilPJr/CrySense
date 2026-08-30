from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import numpy as np

from .audio_features import SAMPLE_RATE
from .models import AudioClassifier, Prediction


@dataclass(frozen=True)
class CryEvent:
    timestamp: str
    label: str
    confidence: float
    trigger_confidence: float
    scores: dict[str, float]


class TwoStagePipeline:
    """IA 1 confirma choro e IA 2 classifica um clip posterior de seis segundos."""

    def __init__(
        self,
        trigger: AudioClassifier,
        type_classifier: AudioClassifier,
        *,
        trigger_threshold: float = 0.80,
        type_threshold: float = 0.75,
        type_margin: float = 0.20,
        confirmation_window: int = 5,
        confirmation_required: int = 3,
        capture_seconds: int = 6,
        on_event: Callable[[CryEvent], None] | None = None,
    ) -> None:
        self.trigger = trigger
        self.type_classifier = type_classifier
        self.trigger_threshold = trigger_threshold
        self.type_threshold = type_threshold
        self.type_margin = type_margin
        self.confirmation_required = confirmation_required
        self.capture_seconds = capture_seconds
        self.on_event = on_event
        self._window: deque[bool] = deque(maxlen=confirmation_window)
        self._capturing: list[np.ndarray] = []
        self._last_trigger_confidence = 0.0
        self.last_trigger: Prediction | None = None
        self.last_type: Prediction | None = None
        self.last_error: str | None = None
        self.phase = "idle"

    def feed_frame(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> CryEvent | None:
        """Recebe um quadro de aproximadamente um segundo do microfone."""
        if self.phase == "capturing_type_audio":
            self._capturing.append(samples.astype(np.float32, copy=True))
            self.phase = "capturing_type_audio"
            if len(self._capturing) < self.capture_seconds:
                return None
            clip = np.concatenate(self._capturing)
            self._capturing.clear()
            return self._classify_type(clip, sample_rate)

        try:
            prediction = self.trigger.predict(samples, sample_rate)
        except Exception as exc:
            self.last_error = str(exc)
            self.phase = "error"
            return None

        self.last_error = None
        self.last_trigger = prediction
        is_cry = prediction.label == "cry" and prediction.confidence >= self.trigger_threshold
        self._window.append(is_cry)
        self._last_trigger_confidence = prediction.confidence if is_cry else 0.0
        self.phase = "monitoring"
        if sum(self._window) >= self.confirmation_required:
            self._capturing.clear()
            self._window.clear()
            self.phase = "capturing_type_audio"
        return None

    def _classify_type(self, clip: np.ndarray, sample_rate: int) -> CryEvent | None:
        try:
            prediction = self.type_classifier.predict(clip, sample_rate)
        except Exception as exc:
            self.last_error = str(exc)
            self.phase = "error"
            return None
        self.last_type = prediction
        values = sorted(prediction.scores.values(), reverse=True)
        margin = values[0] - values[1] if len(values) > 1 else 1.0
        self.phase = "monitoring"
        if prediction.confidence < self.type_threshold or margin < self.type_margin:
            return None
        event = CryEvent(
            timestamp=datetime.now(UTC).isoformat(),
            label=prediction.label,
            confidence=prediction.confidence,
            trigger_confidence=self._last_trigger_confidence,
            scores=prediction.scores,
        )
        if self.on_event:
            self.on_event(event)
        return event

    def status(self) -> dict:
        return {
            "phase": self.phase,
            "trigger_ready": self.trigger.ready,
            "type_ready": self.type_classifier.ready,
            "last_trigger": asdict(self.last_trigger) if self.last_trigger else None,
            "last_type": asdict(self.last_type) if self.last_type else None,
            "last_error": self.last_error,
        }
