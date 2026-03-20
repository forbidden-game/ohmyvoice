from dataclasses import dataclass
import json
import shutil
from pathlib import Path
import numpy as np


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float


# Files from the original model directory that are needed by the tokenizer and
# session, copied verbatim into the quantized cache directory.
_TOKENIZER_FILES = {
    "chat_template.json",
    "generation_config.json",
    "merges.txt",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "vocab.json",
}


def _cache_dir_for(model_id: str, bits: int) -> Path:
    """Return the local cache path for a quantized model variant."""
    safe_name = model_id.replace("/", "--").lower()
    return Path.home() / ".cache" / "ohmyvoice" / "models" / f"{safe_name}-{bits}bit"


def _has_safetensors(path: Path) -> bool:
    return path.is_dir() and any(path.glob("*.safetensors"))


def _save_quantized(model, original_model_path: str, cache_path: Path, bits: int, group_size: int) -> None:
    """Persist quantized weights and supporting files to *cache_path*."""
    import mlx.core as mx
    from mlx.utils import tree_flatten

    cache_path.mkdir(parents=True, exist_ok=True)

    # Save weights
    weights = dict(tree_flatten(model.parameters()))
    mx.save_safetensors(str(cache_path / "model.safetensors"), weights)

    # Save quantization metadata so load_model detects it as quantized
    qconf = {"bits": bits, "group_size": group_size}
    (cache_path / "quantization_config.json").write_text(
        json.dumps(qconf, indent=2), encoding="utf-8"
    )

    # Copy config.json and tokenizer/session support files
    src = Path(original_model_path)
    for fname in ["config.json"] + list(_TOKENIZER_FILES):
        src_file = src / fname
        if src_file.exists():
            shutil.copy2(src_file, cache_path / fname)


class ASREngine:
    def __init__(self, model_id: str = "Qwen/Qwen3-ASR-0.6B"):
        self._model_id = model_id
        self._session = None
        self._quantize_bits: int | None = None

    def load(self, quantize_bits: int = 4) -> None:
        from mlx_qwen3_asr import Session, load_model
        from mlx_qwen3_asr.convert import quantize_model
        import mlx.core as mx

        if quantize_bits in (4, 8):
            cache_path = _cache_dir_for(self._model_id, quantize_bits)
            if _has_safetensors(cache_path):
                # Fast path: load pre-quantized weights directly — no fp16 peak
                model, _ = load_model(str(cache_path))
            else:
                # First run: load fp16, quantize, persist to cache
                model, _ = load_model(self._model_id)
                model = quantize_model(model, bits=quantize_bits)
                mx.eval(model.parameters())
                original_path = getattr(model, "_resolved_model_path", None)
                if original_path:
                    _save_quantized(model, original_path, cache_path, bits=quantize_bits, group_size=64)
        else:
            model, _ = load_model(self._model_id)

        # Limit MLX memory cache to prevent unbounded growth
        mx.set_cache_limit(512 * 1024 * 1024)  # 512MB
        self._quantize_bits = quantize_bits
        self._session = Session(model=model)

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    @property
    def quantize_bits(self) -> int | None:
        return self._quantize_bits

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
        self._quantize_bits = None
        import gc
        gc.collect()
        try:
            import mlx.core as mx
            if hasattr(mx.metal, "clear_cache"):
                mx.metal.clear_cache()
            else:
                old_limit = mx.metal.set_cache_limit(0)
                mx.metal.set_cache_limit(old_limit)
        except (ImportError, AttributeError):
            pass
