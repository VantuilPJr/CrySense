from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .audio_features import decode_wav_bytes
from .models import AudioClassifier, Prediction
from .pipeline import CONFIRMATION_REQUIRED, CONFIRMATION_WINDOW, CryEvent

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _prediction_dict(prediction: Prediction) -> dict:
    return {
        "label": prediction.label,
        "confidence": prediction.confidence,
        "scores": prediction.scores,
    }


def _confirmation_candidate(
    predictions: list[Prediction],
    trigger_threshold: float,
) -> tuple[int, int, int, float] | None:
    """Escolhe a janela 3/5 com maior evidência de choro e desempata pela mais antiga."""
    candidates: list[tuple[int, float, int, int]] = []
    for end_index in range(len(predictions)):
        start_index = max(0, end_index - CONFIRMATION_WINDOW + 1)
        window = predictions[start_index : end_index + 1]
        probabilities = [prediction.scores.get("cry", 0.0) for prediction in window]
        positive_count = sum(probability >= trigger_threshold for probability in probabilities)
        if positive_count >= CONFIRMATION_REQUIRED:
            candidates.append((positive_count, float(np.mean(probabilities)), start_index, end_index))
    if not candidates:
        return None
    positive_count, mean_probability, start_index, end_index = max(
        candidates,
        key=lambda candidate: (candidate[0], candidate[1], -candidate[3]),
    )
    return start_index, end_index, positive_count, mean_probability


def _best_unconfirmed_count(predictions: list[Prediction], trigger_threshold: float) -> int:
    best = 0
    for end_index in range(len(predictions)):
        start_index = max(0, end_index - CONFIRMATION_WINDOW + 1)
        probabilities = (
            prediction.scores.get("cry", 0.0)
            for prediction in predictions[start_index : end_index + 1]
        )
        best = max(best, sum(probability >= trigger_threshold for probability in probabilities))
    return best


def analyze_uploaded_wav(
    payload: bytes,
    filename: str,
    trigger: AudioClassifier,
    type_classifier: AudioClassifier,
    trigger_threshold: float,
    type_threshold: float,
    type_margin: float,
) -> tuple[dict, CryEvent | None]:
    """Classifica um WAV manualmente e devolve um evento quando a decisão é confirmada."""
    safe_filename = Path(filename or "audio.wav").name
    if not safe_filename.lower().endswith(".wav"):
        raise ValueError("Envie um arquivo .wav em PCM.")
    if not payload:
        raise ValueError("O arquivo de áudio está vazio.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("O arquivo é maior que 12 MB.")
    if not trigger.ready or not type_classifier.ready:
        raise RuntimeError("Os modelos de áudio ainda não estão prontos.")

    samples, sample_rate = decode_wav_bytes(payload)
    if samples.size == 0 or sample_rate <= 0:
        raise ValueError("O arquivo não possui amostras de áudio válidas.")

    trigger_frame_samples = max(1, round(sample_rate * trigger.seconds))
    trigger_predictions: list[Prediction] = []
    trigger_windows: list[dict] = []
    for index, start in enumerate(range(0, samples.size, trigger_frame_samples)):
        stop = min(samples.size, start + trigger_frame_samples)
        prediction = trigger.predict(samples[start:stop], sample_rate)
        trigger_predictions.append(prediction)
        trigger_windows.append(
            {
                "index": index,
                "start_seconds": round(start / sample_rate, 3),
                "end_seconds": round(stop / sample_rate, 3),
                **_prediction_dict(prediction),
            }
        )

    trigger_prediction = max(
        trigger_predictions,
        key=lambda prediction: prediction.scores.get("cry", 0.0),
    )
    confirmation = _confirmation_candidate(trigger_predictions, trigger_threshold)
    positive_windows = (
        confirmation[2]
        if confirmation is not None
        else _best_unconfirmed_count(trigger_predictions, trigger_threshold)
    )
    result: dict = {
        "filename": safe_filename,
        "duration_seconds": round(samples.size / sample_rate, 2),
        "sample_rate": sample_rate,
        "trigger": _prediction_dict(trigger_prediction),
        "trigger_windows": trigger_windows,
        "trigger_confirmation": {
            "confirmed": confirmation is not None,
            "positive_windows": positive_windows,
            "required_windows": CONFIRMATION_REQUIRED,
            "window_size": CONFIRMATION_WINDOW,
            "analyzed_windows": len(trigger_predictions),
        },
        "classification": None,
        "alert_triggered": False,
        "message": (
            f"A IA 1 encontrou somente {positive_windows} de {CONFIRMATION_REQUIRED} "
            "janelas de choro necessárias para confirmar este áudio."
        ),
    }
    if confirmation is None:
        return result, None

    _, confirmation_end_index, positive_windows, mean_probability = confirmation
    confirmation_end_sample = min(samples.size, (confirmation_end_index + 1) * trigger_frame_samples)
    type_frame_samples = max(1, round(sample_rate * type_classifier.seconds))
    selected_start = max(0, confirmation_end_sample - type_frame_samples)
    selected_stop = min(samples.size, selected_start + type_frame_samples)
    if selected_stop - selected_start < type_frame_samples and samples.size >= type_frame_samples:
        selected_start = samples.size - type_frame_samples
        selected_stop = samples.size

    type_prediction = type_classifier.predict(samples[selected_start:selected_stop], sample_rate)
    values = sorted(type_prediction.scores.values(), reverse=True)
    margin = values[0] - values[1] if len(values) > 1 else 1.0
    result["trigger_confirmation"].update(
        {
            "positive_windows": positive_windows,
            "mean_cry_confidence": mean_probability,
            "confirmation_end_seconds": round(confirmation_end_sample / sample_rate, 3),
        }
    )
    result["selected_clip"] = {
        "start_seconds": round(selected_start / sample_rate, 3),
        "end_seconds": round(selected_stop / sample_rate, 3),
    }
    result["classification"] = _prediction_dict(type_prediction)
    result["classification"]["margin"] = margin
    if type_prediction.confidence < type_threshold or margin < type_margin:
        result["message"] = (
            "A IA 1 confirmou o choro, mas a IA 2 não atingiu a confiança e a margem "
            "necessárias para gerar o alerta."
        )
        return result, None

    result["message"] = "Choro e tipo confirmados. O mesmo alerta do monitoramento ao vivo foi acionado."
    result["alert_triggered"] = True
    event = CryEvent(
        timestamp=datetime.now(UTC).isoformat(),
        label=type_prediction.label,
        confidence=type_prediction.confidence,
        trigger_confidence=trigger_prediction.confidence,
        scores=type_prediction.scores,
    )
    return result, event
