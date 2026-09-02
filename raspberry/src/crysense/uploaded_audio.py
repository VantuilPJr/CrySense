from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .audio_features import decode_wav_bytes
from .models import AudioClassifier, Prediction
from .pipeline import CryEvent

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MIN_UPLOAD_SECONDS = 3.0


def _prediction_dict(prediction: Prediction) -> dict:
    return {
        "label": prediction.label,
        "confidence": prediction.confidence,
        "scores": prediction.scores,
    }


def analyze_uploaded_wav(
    payload: bytes,
    filename: str,
    type_classifier: AudioClassifier,
    type_threshold: float,
    type_margin: float,
) -> tuple[dict, CryEvent | None]:
    """Envia um choro já conhecido diretamente à IA 2 e gera evento quando o tipo é confirmado."""
    safe_filename = Path(filename or "audio.wav").name
    if not safe_filename.lower().endswith(".wav"):
        raise ValueError("Envie um arquivo .wav em PCM.")
    if not payload:
        raise ValueError("O arquivo de áudio está vazio.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("O arquivo é maior que 12 MB.")
    if not type_classifier.ready:
        raise RuntimeError("O modelo da IA 2 ainda não está pronto.")

    samples, sample_rate = decode_wav_bytes(payload)
    if samples.size == 0 or sample_rate <= 0:
        raise ValueError("O arquivo não possui amostras de áudio válidas.")

    duration_seconds = samples.size / sample_rate
    if duration_seconds < MIN_UPLOAD_SECONDS:
        raise ValueError(
            f"Envie pelo menos {MIN_UPLOAD_SECONDS:.0f} segundos de choro; o ideal é cerca de 6 segundos."
        )
    type_frame_samples = max(1, round(sample_rate * type_classifier.seconds))
    selected_stop = min(samples.size, type_frame_samples)
    type_prediction = type_classifier.predict(samples[:selected_stop], sample_rate)
    values = sorted(type_prediction.scores.values(), reverse=True)
    margin = values[0] - values[1] if len(values) > 1 else 1.0

    result: dict = {
        "filename": safe_filename,
        "duration_seconds": round(duration_seconds, 2),
        "sample_rate": sample_rate,
        "source": "upload",
        "analysis_mode": "uploaded_known_cry",
        "ia1_bypassed": True,
        "selected_clip": {
            "start_seconds": 0.0,
            "end_seconds": round(selected_stop / sample_rate, 3),
            "model_window_seconds": type_classifier.seconds,
            "padded_seconds": round(max(0.0, type_classifier.seconds - duration_seconds), 3),
            "truncated": samples.size > type_frame_samples,
        },
        "classification": {**_prediction_dict(type_prediction), "margin": margin},
        "alert_triggered": False,
        "message": "O choro enviado foi analisado diretamente pela IA 2.",
    }
    if type_prediction.confidence < type_threshold or margin < type_margin:
        result["message"] = (
            "A IA 2 analisou o choro enviado, mas não atingiu a confiança e a margem "
            "necessárias para confirmar cólica ou fome."
        )
        return result, None

    result["message"] = "Tipo do choro confirmado pela IA 2. O mesmo alerta do monitoramento ao vivo foi acionado."
    result["alert_triggered"] = True
    event = CryEvent(
        timestamp=datetime.now(UTC).isoformat(),
        label=type_prediction.label,
        confidence=type_prediction.confidence,
        # Campo legado obrigatório no SQLite: 1.0 representa que o upload foi
        # declarado como choro pelo usuário, não uma inferência da IA 1.
        trigger_confidence=1.0,
        scores=type_prediction.scores,
    )
    return result, event
