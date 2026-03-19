import numpy as np
import pytest
from ohmyvoice.asr import ASREngine


@pytest.fixture(scope="module")
def engine():
    e = ASREngine(model_id="Qwen/Qwen3-ASR-0.6B")
    e.load()
    return e


def test_engine_loads(engine):
    assert engine.is_loaded


def test_transcribe_silence(engine):
    silence = np.zeros(16000 * 2, dtype=np.float32)
    result = engine.transcribe(silence)
    assert isinstance(result.text, str)


def test_transcribe_returns_result_type(engine):
    t = np.linspace(0, 1, 16000, dtype=np.float32)
    tone = (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32)
    result = engine.transcribe(tone)
    assert hasattr(result, "text")
    assert hasattr(result, "language")
