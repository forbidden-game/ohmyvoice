import json
import time
from unittest.mock import MagicMock, patch

import pytest

from ohmyvoice.worker_manager import WorkerManager, PendingJob


def _noop(*a, **kw):
    pass


def _make_manager(**overrides):
    """Create a manager with noop callbacks and mock process."""
    kw = dict(on_result=_noop, on_error=_noop, on_state_change=_noop)
    kw.update(overrides)
    m = WorkerManager(**kw)
    # Inject mock process so _send works without real subprocess
    m._proc = MagicMock()
    m._proc.poll.return_value = None
    m._proc.stdin = MagicMock()
    m._worker_gen = 1
    return m


class TestOnPress:
    def test_idle_to_recording(self):
        m = _make_manager()
        m._app_state = "idle"
        m._worker_state = "ready"
        m._loaded_quantization = "4bit"

        with patch.object(m, "_respawn_worker"):
            result = m.on_press("4bit")

        assert result is True
        assert m._app_state == "recording"

    def test_not_idle_returns_false(self):
        m = _make_manager()
        m._app_state = "recording"

        with patch.object(m, "_respawn_worker"):
            result = m.on_press("4bit")

        assert result is False

    def test_dead_worker_triggers_respawn(self):
        m = _make_manager()
        m._app_state = "idle"
        m._worker_state = "dead"

        with patch.object(m, "_respawn_worker", return_value=2) as mock_respawn:
            m.on_press("4bit")

        mock_respawn.assert_called_once()

    def test_ready_quantization_mismatch_sends_ensure(self):
        m = _make_manager()
        m._app_state = "idle"
        m._worker_state = "ready"
        m._loaded_quantization = "4bit"

        with patch.object(m, "_respawn_worker"):
            m.on_press("8bit")

        calls = m._proc.stdin.write.call_args_list
        sent = [json.loads(c[0][0]) for c in calls]
        assert any(s.get("type") == "ensure_loaded" and s.get("quantization") == "8bit" for s in sent)

    def test_unloaded_worker_sends_ensure(self):
        m = _make_manager()
        m._app_state = "idle"
        m._worker_state = "unloaded"

        with patch.object(m, "_respawn_worker"):
            m.on_press("4bit")

        calls = m._proc.stdin.write.call_args_list
        sent = [json.loads(c[0][0]) for c in calls]
        assert any(s.get("type") == "ensure_loaded" for s in sent)

    def test_respawn_failure_reverts_state(self):
        m = _make_manager()
        m._app_state = "idle"
        m._worker_state = "dead"

        with patch.object(m, "_respawn_worker", side_effect=OSError("no python")):
            result = m.on_press("4bit")

        assert result is False
        assert m._app_state == "idle"


class TestOnRelease:
    def test_ready_sends_transcribe(self, tmp_path):
        m = _make_manager()
        m._app_state = "recording"
        m._worker_state = "ready"
        m._loaded_quantization = "4bit"
        m._desired_quantization = "4bit"

        wav_path = str(tmp_path / "test.wav")
        open(wav_path, "w").close()

        m.on_release(wav_path, 16000, "ctx")

        assert m._app_state == "processing"
        assert m._active_job is not None
        assert m._worker_state == "transcribing"

    def test_loading_creates_pending(self, tmp_path):
        m = _make_manager()
        m._app_state = "recording"
        m._worker_state = "loading"

        wav_path = str(tmp_path / "test.wav")
        open(wav_path, "w").close()

        m.on_release(wav_path, 16000, "ctx")

        assert m._app_state == "processing"
        assert m._pending_job is not None
        assert m._active_job is None

    def test_unloaded_creates_pending(self, tmp_path):
        m = _make_manager()
        m._app_state = "recording"
        m._worker_state = "unloaded"

        wav_path = str(tmp_path / "test.wav")
        open(wav_path, "w").close()

        m.on_release(wav_path, 16000, "ctx")

        assert m._pending_job is not None


class TestOnShortAudio:
    def test_returns_to_idle(self):
        states = []
        m = _make_manager(on_state_change=lambda s: states.append(s))
        m._app_state = "recording"

        m.on_short_audio()

        assert m._app_state == "idle"
        assert "idle" in states


class TestWorkerReady:
    def test_starting_to_unloaded(self):
        m = _make_manager()
        m._worker_state = "starting"

        m._on_worker_ready(1)

        assert m._worker_state == "unloaded"

    def test_stale_gen_ignored(self):
        m = _make_manager()
        m._worker_state = "starting"
        m._worker_gen = 2

        m._on_worker_ready(1)

        assert m._worker_state == "starting"


class TestModelLoading:
    def test_sets_loading_state(self):
        m = _make_manager()
        m._worker_state = "unloaded"

        m._on_model_loading(1, {"type": "model_loading", "quantization": "4bit"})

        assert m._worker_state == "loading"


class TestModelReady:
    def test_with_pending_job_sends_transcribe(self):
        m = _make_manager()
        m._worker_state = "loading"
        m._app_state = "processing"
        m._pending_job = PendingJob(
            job_id="j1", wav_path="/tmp/t.wav", sample_rate=16000,
            context="", created_at=time.time(),
        )

        m._on_model_ready(1, {"type": "model_ready", "quantization": "4bit"})

        assert m._pending_job is None
        assert m._active_job is not None
        assert m._active_job.job_id == "j1"
        assert m._worker_state == "transcribing"

    def test_during_recording_no_ttl(self):
        m = _make_manager()
        m._worker_state = "loading"
        m._app_state = "recording"
        m._pending_job = None

        m._on_model_ready(1, {"type": "model_ready", "quantization": "4bit"})

        assert m._worker_state == "ready"
        assert m._ttl_timer is None

    def test_idle_starts_ttl(self):
        m = _make_manager()
        m._worker_state = "loading"
        m._app_state = "idle"
        m._pending_job = None

        m._on_model_ready(1, {"type": "model_ready", "quantization": "4bit"})

        assert m._worker_state == "ready"
        assert m._loaded_quantization == "4bit"
        assert m._ttl_timer is not None
        m._ttl_timer.cancel()

    def test_initial_load_transitions_to_idle(self):
        states = []
        m = _make_manager(on_state_change=lambda s: states.append(s))
        m._app_state = "loading"
        m._worker_state = "loading"

        m._on_model_ready(1, {"type": "model_ready", "quantization": "4bit"})

        assert m._app_state == "idle"
        assert "idle" in states


class TestTranscribeDone:
    def test_fires_callback_and_resets(self):
        results = []
        m = _make_manager(on_result=lambda *a: results.append(a))
        m._worker_state = "transcribing"
        m._app_state = "processing"
        m._active_job = PendingJob(
            job_id="j1", wav_path="/tmp/t.wav", sample_rate=16000,
            context="", created_at=time.time(),
        )

        m._on_transcribe_done(1, {
            "type": "transcribe_done", "job_id": "j1",
            "text": "hello", "language": "en", "duration_seconds": 1.5,
        })

        assert m._active_job is None
        assert m._worker_state == "ready"
        assert m._app_state == "done"
        assert results == [("hello", "en", 1.5)]

    def test_wrong_job_id_ignored(self):
        results = []
        m = _make_manager(on_result=lambda *a: results.append(a))
        m._worker_state = "transcribing"
        m._active_job = PendingJob(
            job_id="j1", wav_path="/tmp/t.wav", sample_rate=16000,
            context="", created_at=time.time(),
        )

        m._on_transcribe_done(1, {
            "type": "transcribe_done", "job_id": "WRONG",
            "text": "x", "language": "", "duration_seconds": 0,
        })

        assert m._active_job is not None
        assert results == []

    def test_stale_gen_ignored(self):
        results = []
        m = _make_manager(on_result=lambda *a: results.append(a))
        m._worker_gen = 2
        m._worker_state = "transcribing"
        m._active_job = PendingJob(
            job_id="j1", wav_path="/tmp/t.wav", sample_rate=16000,
            context="", created_at=time.time(),
        )

        m._on_transcribe_done(1, {
            "type": "transcribe_done", "job_id": "j1",
            "text": "x", "language": "", "duration_seconds": 0,
        })

        assert results == []


class TestTranscribeError:
    def test_fires_error_callback(self):
        errors = []
        m = _make_manager(on_error=lambda msg: errors.append(msg))
        m._worker_state = "transcribing"
        m._app_state = "processing"
        m._active_job = PendingJob(
            job_id="j1", wav_path="/tmp/t.wav", sample_rate=16000,
            context="", created_at=time.time(),
        )

        m._on_transcribe_error(1, {
            "type": "transcribe_error", "job_id": "j1",
            "message": "boom",
        })

        assert m._active_job is None
        assert m._worker_state == "ready"
        assert m._app_state == "idle"
        assert errors == ["boom"]


class TestWorkerDied:
    def test_active_job_demoted_to_pending(self):
        m = _make_manager()
        m._worker_state = "transcribing"
        m._app_state = "processing"
        m._active_job = PendingJob(
            job_id="j1", wav_path="/tmp/t.wav", sample_rate=16000,
            context="", created_at=time.time(),
        )

        with patch.object(m, "_respawn_worker", return_value=2):
            m._handle_worker_died(1)

        assert m._pending_job is not None
        assert m._pending_job.job_id == "j1"
        assert m._active_job is None

    def test_idle_no_respawn(self):
        m = _make_manager()
        m._worker_state = "ready"
        m._app_state = "idle"

        with patch.object(m, "_respawn_worker") as mock:
            m._handle_worker_died(1)

        mock.assert_not_called()
        assert m._worker_state == "dead"

    def test_during_recording_respawns(self):
        m = _make_manager()
        m._worker_state = "loading"
        m._app_state = "recording"

        with patch.object(m, "_respawn_worker", return_value=2):
            m._handle_worker_died(1)


class TestTTL:
    def test_fires_unload_when_ready_idle(self):
        m = _make_manager()
        m._worker_state = "ready"
        m._app_state = "idle"

        m._on_ttl_expired()

        calls = m._proc.stdin.write.call_args_list
        sent = [json.loads(c[0][0]) for c in calls]
        assert any(s.get("type") == "unload_model" for s in sent)

    def test_ignored_during_recording(self):
        m = _make_manager()
        m._worker_state = "ready"
        m._app_state = "recording"

        m._on_ttl_expired()

        assert m._proc.stdin.write.call_count == 0


class TestDoneTimer:
    def test_transitions_to_idle(self):
        states = []
        m = _make_manager(on_state_change=lambda s: states.append(s))
        m._app_state = "done"

        m._on_done_timer_expired()

        assert m._app_state == "idle"
        assert "idle" in states


class TestModelUnloaded:
    def test_sets_unloaded_state(self):
        m = _make_manager()
        m._worker_state = "ready"
        m._loaded_quantization = "4bit"

        m._on_model_unloaded(1)

        assert m._worker_state == "unloaded"
        assert m._loaded_quantization is None
