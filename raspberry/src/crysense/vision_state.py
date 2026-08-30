from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from time import monotonic


@dataclass(frozen=True)
class VisionSnapshot:
    connected: bool
    state: str
    alert: bool
    label: str | None
    confidence: float | None
    detail: str | None
    updated_at: str | None
    detections: list[dict]


class VisionState:
    """Estado recebido do serviço de visão que executa no computador."""

    def __init__(self, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._state = "offline"
        self._alert = False
        self._label: str | None = None
        self._confidence: float | None = None
        self._detail: str | None = None
        self._updated_at: str | None = None
        self._last_update_monotonic: float | None = None
        self._detections: list[dict] = []

    def update(
        self,
        *,
        state: str,
        alert: bool,
        label: str | None,
        confidence: float | None,
        detail: str | None,
        updated_at: str | None,
        detections: list[dict],
    ) -> bool:
        """Atualiza e informa se este é o início de um novo alerta visual."""
        with self._lock:
            new_alert = alert and (not self._alert or label != self._label)
            self._state = state
            self._alert = alert
            self._label = label
            self._confidence = confidence
            self._detail = detail
            self._updated_at = updated_at
            self._last_update_monotonic = monotonic()
            self._detections = detections
            return new_alert

    def snapshot(self) -> dict:
        with self._lock:
            fresh = self._last_update_monotonic is not None and monotonic() - self._last_update_monotonic <= self.timeout_seconds
            if not fresh:
                return asdict(
                    VisionSnapshot(
                        connected=False,
                        state="offline",
                        alert=False,
                        label=None,
                        confidence=None,
                        detail="Serviço de visão no computador não conectado.",
                        updated_at=self._updated_at,
                        detections=[],
                    )
                )
            return asdict(
                VisionSnapshot(
                    connected=True,
                    state=self._state,
                    alert=self._alert,
                    label=self._label,
                    confidence=self._confidence,
                    detail=self._detail,
                    updated_at=self._updated_at,
                    detections=self._detections,
                )
            )
