from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import RLock
from time import monotonic

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


@dataclass(frozen=True)
class _CandidateFrame:
    samples: np.ndarray
    looks_like_cry: bool


class TwoStagePipeline:
    """IA 1 confirma choro e IA 2 classifica seis segundos alinhados ao choro."""

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
        if confirmation_window <= 0:
            raise ValueError("a janela de confirmação deve ser positiva")
        if not 1 <= confirmation_required <= confirmation_window:
            raise ValueError("a confirmação deve caber na janela")
        if capture_seconds <= 0:
            raise ValueError("a duração da captura deve ser positiva")
        if rearm_required <= 0:
            raise ValueError("o rearme deve exigir ao menos um quadro")

        self.trigger = trigger
        self.type_classifier = type_classifier
        self.trigger_threshold = trigger_threshold
        self.type_threshold = type_threshold
        self.type_margin = type_margin
        self.confirmation_window = confirmation_window
        self.confirmation_required = confirmation_required
        self.capture_seconds = capture_seconds
        self.rearm_required = rearm_required
        self.on_event = on_event

        # Resultados da IA 1 e sinais permanecem alinhados. Assim, áudio ambiente
        # anterior ao primeiro choro não entra por engano no recorte da IA 2.
        self._window: deque[float] = deque(maxlen=confirmation_window)
        self._candidate_frames: deque[_CandidateFrame] = deque(maxlen=confirmation_window)
        self._sample_rate: int | None = None
        self._capturing: list[np.ndarray] = []
        self._capturing_samples = 0

        # Resultado inconclusivo não trava o episódio. Somente um alerta aceito
        # permanece latched até o rearme por silêncio.
        self._alert_latched = False
        self._retry_pending = False
        self._quiet_frames = 0
        self._attempt = 0
        self._last_trigger_confidence = 0.0
        self._last_type_decision: dict | None = None
        self._last_type_decision_at: float | None = None
        self._lock = RLock()

        self.last_trigger: Prediction | None = None
        self.last_type: Prediction | None = None
        self.last_error: str | None = None
        self.phase = "idle"

    def feed_frame(self, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> CryEvent | None:
        """Recebe um quadro de aproximadamente um segundo do microfone."""
        with self._lock:
            return self._feed_frame(samples, sample_rate)

    def _feed_frame(self, samples: np.ndarray, sample_rate: int) -> CryEvent | None:
        if sample_rate <= 0:
            raise ValueError("taxa de amostragem inválida")
        signal = np.asarray(samples, dtype=np.float32).reshape(-1)
        self._ensure_sample_rate(sample_rate)

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
        looks_like_cry = prediction.label == "cry"
        is_cry = looks_like_cry and prediction.confidence >= self.trigger_threshold
        self.phase = "monitoring"

        if self._alert_latched:
            if looks_like_cry:
                self._quiet_frames = 0
            else:
                self._quiet_frames += 1
                if self._quiet_frames >= self.rearm_required:
                    self._reset_episode()
            return None

        if looks_like_cry:
            self._quiet_frames = 0
        else:
            self._quiet_frames += 1
            if self._retry_pending and self._quiet_frames >= self.rearm_required:
                # O choro terminou antes da repetição. O próximo choro será um
                # episódio novo e começará novamente na tentativa 1.
                self._reset_episode()

        confidence = prediction.confidence if is_cry else 0.0
        self._window.append(confidence)
        self._candidate_frames.append(
            _CandidateFrame(
                signal.astype(np.float32, copy=True),
                looks_like_cry,
            )
        )
        if self._positive_windows() >= self.confirmation_required:
            self._last_trigger_confidence = max(self._window)
            self._attempt += 1
            self._retry_pending = False
            self._quiet_frames = 0
            return self._start_type_capture(sample_rate)
        return None

    def _ensure_sample_rate(self, sample_rate: int) -> None:
        if self._sample_rate not in (None, sample_rate):
            self._capturing.clear()
            self._capturing_samples = 0
            self._reset_episode()
            self.phase = "monitoring"
        self._sample_rate = sample_rate

    def _reset_episode(self) -> None:
        self._window.clear()
        self._candidate_frames.clear()
        self._capturing.clear()
        self._capturing_samples = 0
        self._alert_latched = False
        self._retry_pending = False
        self._quiet_frames = 0
        self._attempt = 0

    def _clear_candidate(self) -> None:
        self._window.clear()
        self._candidate_frames.clear()

    def _positive_windows(self) -> int:
        return sum(confidence > 0 for confidence in self._window)

    def _target_samples(self, sample_rate: int) -> int:
        return max(1, round(self.capture_seconds * sample_rate))

    def _start_type_capture(self, sample_rate: int) -> CryEvent | None:
        frames = tuple(self._candidate_frames)
        first_positive = next(
            (index for index, frame in enumerate(frames) if frame.looks_like_cry),
            len(frames),
        )
        selected = frames[first_positive:]
        clip = (
            np.concatenate(tuple(frame.samples for frame in selected))
            if selected
            else np.zeros(0, dtype=np.float32)
        )
        target = self._target_samples(sample_rate)
        clip = clip[:target].astype(np.float32, copy=False)
        self._clear_candidate()
        self._capturing = [clip]
        self._capturing_samples = clip.size
        if self._capturing_samples >= target:
            return self._finish_type_capture(sample_rate)
        self.phase = "capturing_type_audio"
        return None

    def _finish_type_capture(self, sample_rate: int) -> CryEvent | None:
        clip = np.concatenate(self._capturing)
        target = self._target_samples(sample_rate)
        self._capturing.clear()
        self._capturing_samples = 0
        return self._classify_type(clip[:target], sample_rate)

    def _record_type_decision(
        self,
        *,
        state: str,
        reason: str,
        prediction: Prediction | None,
        margin: float | None,
    ) -> None:
        timestamp = datetime.now(UTC).isoformat()
        self._last_type_decision_at = monotonic()
        self._last_type_decision = {
            "state": state,
            "timestamp": timestamp,
            "attempt": self._attempt,
            "prediction": asdict(prediction) if prediction else None,
            "margin": margin,
            "confidence_threshold": self.type_threshold,
            "margin_threshold": self.type_margin,
            "reason": reason,
        }

    def _classify_type(self, clip: np.ndarray, sample_rate: int) -> CryEvent | None:
        try:
            prediction = self.type_classifier.predict(clip, sample_rate)
        except Exception as exc:
            self.last_error = str(exc)
            self.phase = "error"
            self._retry_pending = True
            self._record_type_decision(
                state="error",
                reason="inference_error",
                prediction=None,
                margin=None,
            )
            return None

        self.last_error = None
        self.last_type = prediction
        values = sorted(prediction.scores.values(), reverse=True)
        margin = values[0] - values[1] if len(values) > 1 else 1.0
        confidence_ok = prediction.confidence >= self.type_threshold
        margin_ok = margin >= self.type_margin
        self.phase = "monitoring"

        if not confidence_ok or not margin_ok:
            if not confidence_ok and not margin_ok:
                reason = "low_confidence_and_margin"
            elif not confidence_ok:
                reason = "low_confidence"
            else:
                reason = "low_margin"
            self._retry_pending = True
            self._alert_latched = False
            self._quiet_frames = 0
            self._clear_candidate()
            self._record_type_decision(
                state="inconclusive",
                reason=reason,
                prediction=prediction,
                margin=margin,
            )
            return None

        self._retry_pending = False
        self._alert_latched = True
        self._quiet_frames = 0
        self._clear_candidate()
        self._record_type_decision(
            state="accepted",
            reason="accepted",
            prediction=prediction,
            margin=margin,
        )
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
        with self._lock:
            return self._status()

    def _status(self) -> dict:
        decision = None
        if self._last_type_decision is not None:
            decision = dict(self._last_type_decision)
            decision["age_seconds"] = (
                max(0.0, monotonic() - self._last_type_decision_at)
                if self._last_type_decision_at is not None
                else None
            )
            decision["retry_scheduled"] = self._retry_pending

        target = self._target_samples(self._sample_rate or SAMPLE_RATE)
        capture_progress = (
            min(1.0, self._capturing_samples / target)
            if self.phase == "capturing_type_audio"
            else 0.0
        )
        episode_active = self._alert_latched or self._retry_pending or self.phase == "capturing_type_audio"
        return {
            "phase": self.phase,
            "trigger_ready": self.trigger.ready,
            "type_ready": self.type_classifier.ready,
            "last_trigger": asdict(self.last_trigger) if self.last_trigger else None,
            "last_type": asdict(self.last_type) if self.last_type else None,
            "last_type_decision": decision,
            "confirmation": {
                "positive_windows": self._positive_windows(),
                "required_windows": self.confirmation_required,
                "window_size": self.confirmation_window,
                "evaluated_windows": len(self._window),
            },
            "capture_progress": capture_progress,
            "type_attempt": self._attempt,
            "last_error": self.last_error,
            "episode_active": episode_active,
            "alert_latched": self._alert_latched,
            "armed": not self._alert_latched and self.phase != "capturing_type_audio",
        }
