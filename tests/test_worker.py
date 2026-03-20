import json
import wave
from io import StringIO
from unittest.mock import MagicMock

import numpy as np
import pytest

from ohmyvoice.worker import ASRWorker


def _make_worker(engine=None):
    if engine is None:
        engine = MagicMock()
        engine.is_loaded = False
        engine.quantize_bits = None
    stdout = StringIO()
    worker = ASRWorker(engine=engine, stdout=stdout)
    return worker, stdout


def _messages(stdout):
    stdout.seek(0)
    return [json.loads(line) for line in stdout if line.strip()]


def _write_test_wav(path, duration_s=1.0, sr=16000):
    """Write a valid mono 16-bit wav file."""
    samples = int(sr * duration_s)
    audio = np.zeros(samples, dtype=np.float32)
    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(audio_int16.tobytes())


class TestWorkerReady:
    def test_sends_worker_ready(self):
        engine = MagicMock()
        engine.is_loaded = False
        stdin = StringIO('{"type":"shutdown"}\n')
        stdout = StringIO()
        worker = ASRWorker(engine=engine, stdin=stdin, stdout=stdout)
        with pytest.raises(SystemExit):
            worker.run()
        msgs = _messages(stdout)
        assert msgs[0]["type"] == "worker_ready"


class TestEnsureLoaded:
    def test_cold_load(self):
        worker, stdout = _make_worker()
        worker._engine.is_loaded = False
        worker._dispatch({"type": "ensure_loaded", "quantization": "4bit"})

        worker._engine.load.assert_called_once_with(quantize_bits=4)
        msgs = _messages(stdout)
        types = [m["type"] for m in msgs]
        assert "model_loading" in types
        assert "model_ready" in types
        assert msgs[-1]["quantization"] == "4bit"

    def test_already_loaded_matching_quantization(self):
        worker, stdout = _make_worker()
        worker._engine.is_loaded = True
        worker._engine.quantize_bits = 4
        worker._dispatch({"type": "ensure_loaded", "quantization": "4bit"})

        worker._engine.load.assert_not_called()
        msgs = _messages(stdout)
        assert msgs[0]["type"] == "model_ready"

    def test_quantization_mismatch_reloads(self):
        worker, stdout = _make_worker()
        worker._engine.is_loaded = True
        worker._engine.quantize_bits = 4
        worker._dispatch({"type": "ensure_loaded", "quantization": "8bit"})

        worker._engine.unload.assert_called_once()
        worker._engine.load.assert_called_once_with(quantize_bits=8)


class TestTranscribeFile:
    def test_success(self, tmp_path):
        wav_path = str(tmp_path / "test.wav")
        _write_test_wav(wav_path)

        engine = MagicMock()
        engine.is_loaded = True
        result_mock = MagicMock()
        result_mock.text = "hello"
        result_mock.language = "en"
        result_mock.duration_seconds = 1.0
        engine.transcribe.return_value = result_mock

        worker, stdout = _make_worker(engine=engine)
        worker._dispatch({
            "type": "transcribe_file",
            "job_id": "j1",
            "wav_path": wav_path,
            "sample_rate": 16000,
            "context": "test",
        })

        msgs = _messages(stdout)
        assert msgs[0]["type"] == "transcribe_done"
        assert msgs[0]["job_id"] == "j1"
        assert msgs[0]["text"] == "hello"
        assert msgs[0]["duration_seconds"] == 1.0

    def test_file_not_found(self):
        engine = MagicMock()
        worker, stdout = _make_worker(engine=engine)
        worker._dispatch({
            "type": "transcribe_file",
            "job_id": "j2",
            "wav_path": "/nonexistent.wav",
            "sample_rate": 16000,
        })

        msgs = _messages(stdout)
        assert msgs[0]["type"] == "transcribe_error"
        assert msgs[0]["job_id"] == "j2"

    def test_engine_error(self, tmp_path):
        """Engine raises during transcription — valid wav, engine fails."""
        wav_path = str(tmp_path / "test.wav")
        _write_test_wav(wav_path)

        engine = MagicMock()
        engine.transcribe.side_effect = RuntimeError("inference failed")
        worker, stdout = _make_worker(engine=engine)
        worker._dispatch({
            "type": "transcribe_file",
            "job_id": "j3",
            "wav_path": wav_path,
            "sample_rate": 16000,
        })

        msgs = _messages(stdout)
        assert msgs[0]["type"] == "transcribe_error"
        assert msgs[0]["job_id"] == "j3"
        assert "inference failed" in msgs[0]["message"]

    def test_cleans_up_wav_file(self, tmp_path):
        wav_path = str(tmp_path / "test.wav")
        _write_test_wav(wav_path)

        engine = MagicMock()
        result_mock = MagicMock()
        result_mock.text = "x"
        result_mock.language = ""
        result_mock.duration_seconds = 1.0
        engine.transcribe.return_value = result_mock

        worker, stdout = _make_worker(engine=engine)
        worker._dispatch({
            "type": "transcribe_file",
            "job_id": "j4",
            "wav_path": wav_path,
            "sample_rate": 16000,
        })

        import os
        assert not os.path.exists(wav_path)


class TestUnloadModel:
    def test_sends_model_unloaded(self):
        worker, stdout = _make_worker()
        worker._dispatch({"type": "unload_model"})

        worker._engine.unload.assert_called_once()
        msgs = _messages(stdout)
        assert msgs[0]["type"] == "model_unloaded"


class TestUnknownMessage:
    def test_returns_error(self):
        worker, stdout = _make_worker()
        worker._dispatch({"type": "bogus_command"})
        msgs = _messages(stdout)
        assert msgs[0]["type"] == "worker_error"
