from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float


class ASREngine:
    def __init__(self, model_id: str = "Qwen/Qwen3-ASR-0.6B"):
        self._model_id = model_id
        self._session = None

    def load(self) -> None:
        from mlx_qwen3_asr import Session
        self._session = Session(model=self._model_id)

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    def transcribe(
        self,
        audio: np.ndarray,
        context: str = "",
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load() first.")
        duration = len(audio) / sample_rate
        # mlx-qwen3-asr Python API uses `context` param (injected as system message).
        kwargs = {}
        if context:
            kwargs["context"] = context
        result = self._session.transcribe(
            (audio, sample_rate),
            **kwargs,
        )
        return TranscriptionResult(
            text=result.text.strip(),
            language=getattr(result, "language", ""),
            duration_seconds=duration,
        )

    def unload(self) -> None:
        self._session = None
