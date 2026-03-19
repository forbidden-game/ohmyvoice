import numpy as np
from ohmyvoice.recorder import Recorder


def test_recorder_returns_numpy_array():
    rec = Recorder(sample_rate=16000)
    rec.start()
    import time; time.sleep(1)
    audio = rec.stop()
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert len(audio) > 0
    assert audio.ndim == 1


def test_recorder_duration():
    rec = Recorder(sample_rate=16000)
    rec.start()
    import time; time.sleep(0.5)
    audio = rec.stop()
    duration = len(audio) / 16000
    assert 0.3 < duration < 1.0


def test_list_devices():
    devices = Recorder.list_input_devices()
    assert isinstance(devices, list)
    assert len(devices) > 0
    assert "name" in devices[0]
