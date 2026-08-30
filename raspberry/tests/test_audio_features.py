import numpy as np

from crysense.audio_features import (
    FEATURE_NAMES,
    SAMPLE_RATE,
    extract_features,
    prepare_signal,
)


def test_prepare_signal_resamples_and_pads() -> None:
    source = np.ones(8_000, dtype=np.float32)
    prepared = prepare_signal(source, 8_000, seconds=1.0)
    assert prepared.shape == (SAMPLE_RATE,)
    assert np.allclose(prepared, 1.0)


def test_feature_vector_has_stable_schema() -> None:
    samples = np.sin(2 * np.pi * 440 * np.arange(SAMPLE_RATE) / SAMPLE_RATE).astype(np.float32)
    features = extract_features(samples)
    assert features.vector.shape == (len(FEATURE_NAMES),)
    assert set(features.details) == set(FEATURE_NAMES)
    assert features.details["rms"] > 0
