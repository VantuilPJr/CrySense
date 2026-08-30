from __future__ import annotations

import contextlib
import io
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
EPSILON = 1e-9
FEATURE_NAMES = (
    "rms",
    "peak",
    "zcr",
    "centroid",
    "rolloff85",
    "bandwidth",
    "flatness",
    "flux",
    "modulation",
    "frame_rms_mean",
    "frame_rms_std",
)


@dataclass(frozen=True)
class AudioFeatures:
    vector: np.ndarray
    details: dict[str, float]


def _decode_wav_file(wav_file: wave.Wave_read) -> tuple[np.ndarray, int]:
    """Converte uma origem WAV PCM já aberta para sinal mono normalizado."""
    channels = wav_file.getnchannels()
    sample_rate = wav_file.getframerate()
    width = wav_file.getsampwidth()
    raw = wav_file.readframes(wav_file.getnframes())

    if width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Largura PCM não suportada: {width * 8} bits")

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples.astype(np.float32), sample_rate


def decode_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Lê WAV PCM e devolve amostras normalizadas entre -1 e 1."""
    with contextlib.closing(wave.open(str(path), "rb")) as wav_file:
        return _decode_wav_file(wav_file)


def decode_wav_bytes(payload: bytes) -> tuple[np.ndarray, int]:
    """Lê uma carga WAV PCM recebida pelo painel sem gravá-la em disco."""
    try:
        with contextlib.closing(wave.open(io.BytesIO(payload), "rb")) as wav_file:
            return _decode_wav_file(wav_file)
    except (wave.Error, EOFError) as exc:
        raise ValueError("Envie um arquivo WAV PCM válido.") from exc


def resample_linear(samples: np.ndarray, source_rate: int, target_rate: int = SAMPLE_RATE) -> np.ndarray:
    if source_rate == target_rate:
        return samples.astype(np.float32, copy=False)
    if samples.size == 0:
        return np.zeros(0, dtype=np.float32)
    target_len = max(1, round(samples.size * target_rate / source_rate))
    old_axis = np.linspace(0.0, 1.0, samples.size, endpoint=True)
    new_axis = np.linspace(0.0, 1.0, target_len, endpoint=True)
    return np.interp(new_axis, old_axis, samples).astype(np.float32)


def prepare_signal(
    samples: np.ndarray,
    sample_rate: int,
    *,
    seconds: float,
    target_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Converte para 16 kHz mono e fixa a janela com corte/preenchimento de silêncio."""
    signal = resample_linear(samples, sample_rate, target_rate)
    desired = int(target_rate * seconds)
    if signal.size < desired:
        signal = np.pad(signal, (0, desired - signal.size))
    else:
        signal = signal[:desired]
    return signal.astype(np.float32, copy=False)


def _frames(samples: np.ndarray, frame_size: int = 512, hop_size: int = 256) -> np.ndarray:
    if samples.size < frame_size:
        samples = np.pad(samples, (0, frame_size - samples.size))
    count = 1 + (samples.size - frame_size) // hop_size
    shape = (count, frame_size)
    strides = (samples.strides[0] * hop_size, samples.strides[0])
    return np.lib.stride_tricks.as_strided(samples, shape=shape, strides=strides).copy()


def extract_features(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> AudioFeatures:
    """Extrai 11 características leves, adequadas ao Random Forest no Pi 3B."""
    signal = samples.astype(np.float32, copy=False)
    frames = _frames(signal)
    windowed = frames * np.hanning(512).astype(np.float32)
    magnitude = np.abs(np.fft.rfft(windowed, axis=1)).astype(np.float32) + EPSILON
    power = magnitude * magnitude
    frequencies = np.fft.rfftfreq(512, d=1.0 / sample_rate).astype(np.float32)

    rms = float(np.sqrt(np.mean(signal * signal) + EPSILON))
    peak = float(np.max(np.abs(signal)) if signal.size else 0.0)
    zcr = float(np.mean(np.abs(np.diff(np.signbit(signal).astype(np.int8))))) if signal.size > 1 else 0.0
    total_power = np.sum(power, axis=1) + EPSILON
    centroid_frames = np.sum(power * frequencies[None, :], axis=1) / total_power
    centroid = float(np.mean(centroid_frames))
    cumulative = np.cumsum(power, axis=1)
    rolloff_indices = np.argmax(cumulative >= 0.85 * total_power[:, None], axis=1)
    rolloff = float(np.mean(frequencies[rolloff_indices]))
    bandwidth = float(np.mean(np.sqrt(np.sum(((frequencies[None, :] - centroid_frames[:, None]) ** 2) * power, axis=1) / total_power)))
    flatness = float(np.mean(np.exp(np.mean(np.log(magnitude), axis=1)) / (np.mean(magnitude, axis=1) + EPSILON)))
    flux = float(np.mean(np.sqrt(np.mean((magnitude[1:] - magnitude[:-1]) ** 2, axis=1)))) if magnitude.shape[0] > 1 else 0.0
    frame_rms = np.sqrt(np.mean(windowed * windowed, axis=1) + EPSILON)
    frame_rms_mean = float(np.mean(frame_rms))
    frame_rms_std = float(np.std(frame_rms))
    modulation = float(frame_rms_std / (frame_rms_mean + EPSILON))

    values = (rms, peak, zcr, centroid, rolloff, bandwidth, flatness, flux, modulation, frame_rms_mean, frame_rms_std)
    return AudioFeatures(vector=np.asarray(values, dtype=np.float32), details=dict(zip(FEATURE_NAMES, values, strict=True)))


def features_from_wav(path: str | Path, seconds: float) -> AudioFeatures:
    samples, sample_rate = decode_wav(path)
    return extract_features(prepare_signal(samples, sample_rate, seconds=seconds))
