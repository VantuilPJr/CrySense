from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio_features import AudioFeatures, extract_features, prepare_signal


def _canonical_label(value: str) -> str:
    normalized = (value or "").strip().lower()
    aliases = {
        "choro": "cry",
        "ruido": "noise",
        "ruído": "noise",
        "colica": "colic",
        "cólica": "colic",
        "fome": "hunger",
    }
    return aliases.get(normalized, normalized)


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float
    scores: dict[str, float]
    features: dict[str, float]


class AudioClassifier:
    """Wrapper seguro em torno de um modelo sklearn serializado com joblib."""

    def __init__(self, model_path: Path, labels: Iterable[str], seconds: float) -> None:
        self.model_path = Path(model_path)
        self.labels = tuple(_canonical_label(label) for label in labels)
        self.seconds = seconds
        self.model = None
        self.load_error: str | None = None

    @property
    def ready(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        self.model = None
        self.load_error = None
        if not self.model_path.exists():
            self.load_error = f"modelo ausente: {self.model_path}"
            return
        try:
            import joblib

            self.model = joblib.load(self.model_path)
        except Exception as exc:  # O dashboard precisa continuar disponível sem o modelo.
            self.load_error = f"falha ao carregar modelo: {exc}"

    def predict(self, samples: np.ndarray, sample_rate: int) -> Prediction:
        if self.model is None:
            raise RuntimeError(self.load_error or "modelo não carregado")
        signal = prepare_signal(samples, sample_rate, seconds=self.seconds)
        feature_set = extract_features(signal)
        scores = self._scores(feature_set)
        label = max(self.labels, key=lambda item: scores.get(item, 0.0))
        return Prediction(label=label, confidence=float(scores[label]), scores=scores, features=feature_set.details)

    def _scores(self, features: AudioFeatures) -> dict[str, float]:
        vector = features.vector.reshape(1, -1)
        scores = {label: 0.0 for label in self.labels}
        if hasattr(self.model, "predict_proba"):
            probabilities = np.asarray(self.model.predict_proba(vector)[0], dtype=np.float32)
            classes = getattr(self.model, "classes_", self.labels)
            for raw_label, probability in zip(classes, probabilities, strict=True):
                label = _canonical_label(str(raw_label))
                if label in scores:
                    scores[label] += max(0.0, float(probability))
        else:
            label = _canonical_label(str(self.model.predict(vector)[0]))
            if label in scores:
                scores[label] = 1.0

        total = sum(scores.values())
        if total <= 0:
            return {label: 1.0 / len(scores) for label in scores}
        return {label: value / total for label, value in scores.items()}


def write_model_metadata(path: Path, metadata: dict) -> None:
    path.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
