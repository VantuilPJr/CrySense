from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .audio_features import decode_wav_bytes
from .models import AudioClassifier, Prediction
from .pipeline import CryEvent

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _prediction_dict(prediction: Prediction) -> dict:
    return {
        "label": prediction.label,
        "confidence": prediction.confidence,
        "scores": prediction.scores,
    }


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

    trigger_prediction = trigger.predict(samples, sample_rate)
    result: dict = {
        "filename": safe_filename,
        "duration_seconds": round(samples.size / sample_rate, 2),
        "sample_rate": sample_rate,
        "trigger": _prediction_dict(trigger_prediction),
        "classification": None,
        "message": "A IA 1 identificou ruído ou não confirmou choro neste áudio.",
    }
    if trigger_prediction.label != "cry" or trigger_prediction.confidence < trigger_threshold:
        return result, None

    type_prediction = type_classifier.predict(samples, sample_rate)
    values = sorted(type_prediction.scores.values(), reverse=True)
    margin = values[0] - values[1] if len(values) > 1 else 1.0
    if type_prediction.confidence < type_threshold or margin < type_margin:
        result["message"] = "A IA 1 confirmou choro, mas a IA 2 não atingiu a confiança necessária para gerar alerta."
        return result, None

    result["classification"] = _prediction_dict(type_prediction)
    result["message"] = "Choro e tipo confirmados. O mesmo alerta do monitoramento ao vivo foi acionado."
    event = CryEvent(
        timestamp=datetime.now(UTC).isoformat(),
        label=type_prediction.label,
        confidence=type_prediction.confidence,
        trigger_confidence=trigger_prediction.confidence,
        scores=type_prediction.scores,
    )
    return result, event
