from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import numpy as np

from .audio_features import SAMPLE_RATE
from .models import AudioClassifier, Prediction

CONFIRMATION_WINDOW = 5
CONFIRMATION_REQUIRED = 3


@dataclass(frozen=True)
class CryEvent:
    timestamp: str
    label: str
    confidence: float
    trigger_confidence: float
    scores: dict[str, float]


class TwoStagePipeline:
    """IA 1 confirma choro e IA 2 classifica um clip que inclui o gatilho."""

    def __init__(
        self,
        trigger: AudioClassifier,
        type_classifier: AudioClassifier,
        *,
        trigger_threshold: float = 0.80,
        type_threshold: float = 0.68,
        type_margin: float = 0.20,
        confirmation_window: int = CONFIRMATION_WINDOW,
        confirmation_required: int = CONFIRMATION_REQUIRED,
        capture_seconds: int = 6,
        rearm_required: int = 3,
        on_event: Callable[[CryEvent], None] | None = None,
    ) -> None:
        self.trigger = trigger
        self.type_classifier = type_classifier
        self.trigger_threshold = trigger_threshold
        self.type_threshold = type_threshold
        self.type_margin = type_margin
        self.confirmation_required = confirmation_required
        self.capture_seconds = capture_seconds
        self.rearm_required = rearm_required
        self.on_event = on_event
        self._window: deque[float] = deque(maxlen=confirmation_window)
        self._history: deque[np.ndarray] = deque()
        self._history_samples = 0
        self._history_sample_rate: int | None = None
        self._capturing: list[np.ndarray] = []
        self._capturing_samples = 0
        self._episode_active = False
        self._quiet_frames = 0
        self._last_trigger_confidence = 0.0
        self.last_trigger: Prediction | None = None
        self.last_type: Prediction | None = None
        self.last_error: str | None = None
        self.phase = "idle"

    def feed_frame(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> CryEvent | None:
        """Recebe um quadro de aproximadamente um segundo do microfone."""
        signal = np.asarray(samples, dtype=np.float32).reshape(-1)
        self._append_history(signal, sample_rate)

        if self.phase == "capturing_type_audio":
            copied = signal.astype(np.float32, copy=True)
            self._capturing.append(copied)
            self._capturing_samples += copied.size
            if self._capturing_samples < self._target_samples(sample_rate):
                return None
            return self._finish_type_capture(sample_rate)

        try:
            prediction = self.trigger.predict(signal, sample_rate)
        except Exception as exc:
            self.last_error = str(exc)
            self.phase = "error"
            return None

        self.last_error = None
        self.last_trigger = prediction
        is_cry = prediction.label == "cry" and prediction.confidence >= self.trigger_threshold
        self.phase = "monitoring"

        if self._episode_active:
            if is_cry:
                self._quiet_frames = 0
            else:
                self._quiet_frames += 1
                if self._quiet_frames >= self.rearm_required:
                    self._episode_active = False
                    self._quiet_frames = 0
                    self._window.clear()
            return None

        self._window.append(prediction.confidence if is_cry else 0.0)
        if sum(confidence > 0 for confidence in self._window) >= self.confirmation_required:
            confirmation_frames = len(self._window)
            self._last_trigger_confidence = max(self._window)
            self._window.clear()
            self._episode_active = True
            self._quiet_frames = 0
            return self._start_type_capture(sample_rate, confirmation_frames)
        return None

    def _target_samples(self, sample_rate: int) -> int:
        return max(1, round(self.capture_seconds * sample_rate))

    def _append_history(self, samples: np.ndarray, sample_rate: int) -> None:
        if sample_rate <= 0:
            raise ValueError("taxa de amostragem inválida")
        if self._history_sample_rate not in (None, sample_rate):
            self._history.clear()
            self._history_samples = 0
            self._capturing.clear()
            self._capturing_samples = 0
            self._window.clear()
            self._episode_active = False
            self._quiet_frames = 0
            self.phase = "monitoring"
        self._history_sample_rate = sample_rate
        if samples.size:
            copied = samples.astype(np.float32, copy=True)
            self._history.append(copied)
            self._history_samples += copied.size

        excess = self._history_samples - self._target_samples(sample_rate)
        while excess > 0 and self._history:
            oldest = self._history[0]
            if oldest.size <= excess:
                self._history.popleft()
                self._history_samples -= oldest.size
                excess -= oldest.size
                continue
            self._history[0] = oldest[excess:].copy()
            self._history_samples -= excess
            excess = 0

    def _history_clip(self, sample_rate: int, sample_count: int | None = None) -> np.ndarray:
        if not self._history:
            return np.zeros(0, dtype=np.float32)
        clip = np.concatenate(tuple(self._history))
        target = sample_count or self._target_samples(sample_rate)
        return clip[-target:].astype(np.float32, copy=False)

    def _start_type_capture(self, sample_rate: int, confirmation_frames: int) -> CryEvent | None:
        trigger_seconds = float(getattr(self.trigger, "seconds", 1.0))
        pre_roll_seconds = min(float(self.capture_seconds), confirmation_frames * trigger_seconds)
        pre_roll_samples = min(
            self._history_samples,
            max(1, round(pre_roll_seconds * sample_rate)),
        )
        clip = self._history_clip(sample_rate, pre_roll_samples).copy()
        self._capturing = [clip]
        self._capturing_samples = clip.size
        if self._capturing_samples >= self._target_samples(sample_rate):
            return self._finish_type_capture(sample_rate)
        self.phase = "capturing_type_audio"
        return None

    def _finish_type_capture(self, sample_rate: int) -> CryEvent | None:
        clip = np.concatenate(self._capturing)
        target = self._target_samples(sample_rate)
        self._capturing.clear()
        self._capturing_samples = 0
        return self._classify_type(clip[-target:], sample_rate)

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
            "armed": not self._episode_active,
        }
