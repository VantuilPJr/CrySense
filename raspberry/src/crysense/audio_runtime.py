from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np

from .pipeline import CryEvent, TwoStagePipeline


class AudioRuntime:
    """Captura contínua no ALSA/PortAudio e envia o canal escolhido ao pipeline."""

    def __init__(
        self,
        pipeline: TwoStagePipeline,
        *,
        input_device: str | None = None,
        input_channels: int = 1,
        input_channel: int = 0,
        on_event: Callable[[CryEvent], None] | None = None,
        on_frame: Callable[[], None] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.input_device = input_device
        self.input_channels = input_channels
        self.input_channel = input_channel
        self.on_event = on_event
        self.on_frame = on_frame
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: str | None = None
        self.capture_sample_rate: int | None = None
        self.level_rms: float | None = None
        self.level_peak: float | None = None
        self.last_frame_at: str | None = None
        self._last_frame_monotonic: float | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def listening(self) -> bool:
        return bool(
            self.running
            and self.error is None
            and self._last_frame_monotonic is not None
            and time.monotonic() - self._last_frame_monotonic <= 3
        )

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="crysense-audio", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        try:
            import sounddevice as sound

            if self.input_channels < 1 or not 0 <= self.input_channel < self.input_channels:
                raise ValueError("configuração inválida dos canais de entrada de áudio")
            device_info = sound.query_devices(self.input_device, "input")
            self.capture_sample_rate = round(float(device_info["default_samplerate"]))
            if self.capture_sample_rate <= 0:
                raise RuntimeError("o dispositivo de entrada não informou uma taxa de amostragem válida")
            with sound.InputStream(
                samplerate=self.capture_sample_rate,
                blocksize=self.capture_sample_rate,
                channels=self.input_channels,
                dtype="float32",
                device=self.input_device,
            ) as stream:
                while not self._stop.is_set():
                    block, _overflowed = stream.read(self.capture_sample_rate)
                    selected = np.asarray(block[:, self.input_channel], dtype=np.float32)
                    self.level_rms = float(np.sqrt(np.mean(np.square(selected, dtype=np.float64))))
                    self.level_peak = float(np.max(np.abs(selected)))
                    self.last_frame_at = datetime.now(UTC).isoformat()
                    self._last_frame_monotonic = time.monotonic()
                    event = self.pipeline.feed_frame(
                        selected, sample_rate=self.capture_sample_rate
                    )
                    if event and self.on_event:
                        self.on_event(event)
                    if self.on_frame:
                        self.on_frame()
        except Exception as exc:
            self.error = str(exc)


class PinkNoisePlayer:
    """Reproduz ruído suave durante uma ocorrência de cólica; não bloqueia a captura."""

    def __init__(self, output_device: str | None = None, output_channels: int = 2) -> None:
        self.output_device = output_device
        self.output_channels = output_channels
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def play(self, duration_seconds: int = 60) -> None:
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(duration_seconds,), name="crysense-noise", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self, duration_seconds: int) -> None:
        try:
            import sounddevice as sound

            device_info = sound.query_devices(self.output_device, "output")
            output_sample_rate = round(float(device_info["default_samplerate"]))
            if output_sample_rate <= 0 or self.output_channels < 1:
                return
            remaining = duration_seconds * output_sample_rate
            previous = 0.0
            with sound.OutputStream(
                samplerate=output_sample_rate,
                channels=self.output_channels,
                dtype="float32",
                device=self.output_device,
            ) as stream:
                while remaining > 0 and not self._stop.is_set():
                    count = min(1024, remaining)
                    white = np.random.normal(0.0, 0.22, count).astype(np.float32)
                    pink = np.empty(count, dtype=np.float32)
                    for index, value in enumerate(white):
                        previous = 0.985 * previous + 0.15 * float(value)
                        pink[index] = previous
                    stream.write(np.repeat(pink.reshape(-1, 1), self.output_channels, axis=1))
                    remaining -= count
        except Exception:
            # Reprodução é terapêutica opcional; uma falha nunca interrompe a monitoração.
            return
