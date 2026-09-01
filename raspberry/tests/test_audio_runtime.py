import sys
import threading
import time
from types import SimpleNamespace
from typing import ClassVar

import numpy as np

from crysense.audio_runtime import PinkNoisePlayer


class CapturingStream:
    writes: ClassVar[list[np.ndarray]] = []
    opened: ClassVar[int] = 0

    def __init__(self, **_kwargs) -> None:
        pass

    def __enter__(self):
        type(self).opened += 1
        return self

    def __exit__(self, *_args) -> None:
        pass

    def write(self, samples: np.ndarray) -> None:
        type(self).writes.append(samples.copy())


def fake_sounddevice(sample_rate: int = 100):
    return SimpleNamespace(
        query_devices=lambda *_args: {"default_samplerate": sample_rate},
        OutputStream=CapturingStream,
    )


def render(monkeypatch, volume: float) -> np.ndarray:
    CapturingStream.writes = []
    CapturingStream.opened = 0
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice())
    monkeypatch.setattr(
        np.random,
        "normal",
        lambda _mean, deviation, count: np.full(count, deviation * 0.1, dtype=np.float32),
    )
    player = PinkNoisePlayer(output_channels=1, volume=volume)
    player._run(1, threading.Event())
    return np.concatenate(CapturingStream.writes)[:, 0]


def test_volume_scales_signal_and_ramp_avoids_abrupt_edges(monkeypatch) -> None:
    full = render(monkeypatch, 1.0)
    reduced = render(monkeypatch, 0.25)

    np.testing.assert_allclose(reduced, full * 0.25, rtol=1e-6, atol=1e-7)
    assert abs(full[0]) < abs(full[len(full) // 2]) * 0.02
    assert abs(full[-1]) < abs(full[len(full) // 2]) * 0.10


def test_invalid_and_disabled_volumes_are_safe(monkeypatch) -> None:
    assert PinkNoisePlayer(volume=float("nan")).volume == 0.10
    assert PinkNoisePlayer(volume=float("inf")).volume == 0.10
    assert PinkNoisePlayer(volume=-1).volume == 0
    assert PinkNoisePlayer(volume=2).volume == 1

    CapturingStream.opened = 0
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice())
    PinkNoisePlayer(volume=0)._run(60, threading.Event())
    assert CapturingStream.opened == 0


def test_repeated_play_never_opens_two_streams(monkeypatch) -> None:
    class SlowStream(CapturingStream):
        active: ClassVar[int] = 0
        max_active: ClassVar[int] = 0
        started: ClassVar[threading.Event] = threading.Event()

        def __enter__(self):
            type(self).active += 1
            type(self).max_active = max(type(self).max_active, type(self).active)
            type(self).started.set()
            return self

        def __exit__(self, *_args) -> None:
            type(self).active -= 1

        def write(self, _samples: np.ndarray) -> None:
            time.sleep(0.01)

    sound = SimpleNamespace(
        query_devices=lambda *_args: {"default_samplerate": 100_000},
        OutputStream=SlowStream,
    )
    monkeypatch.setitem(sys.modules, "sounddevice", sound)
    player = PinkNoisePlayer(output_channels=1)

    player.play(60)
    assert SlowStream.started.wait(1)
    SlowStream.started.clear()
    player.play(60)
    assert SlowStream.started.wait(1)
    player.stop()

    assert SlowStream.max_active == 1
