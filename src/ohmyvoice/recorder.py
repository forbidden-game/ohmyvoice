import threading
import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, sample_rate: int = 16000, device: str | int | None = None):
        self._sample_rate = sample_rate
        self._device = device
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks)
        return audio.flatten()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None and self._stream.active

    @property
    def duration(self) -> float:
        with self._lock:
            total = sum(len(c) for c in self._chunks)
        return total / self._sample_rate

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self._chunks.append(indata.copy())

    @staticmethod
    def list_input_devices() -> list[dict]:
        devices = sd.query_devices()
        result = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                result.append({
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "sample_rate": d["default_samplerate"],
                })
        return result
