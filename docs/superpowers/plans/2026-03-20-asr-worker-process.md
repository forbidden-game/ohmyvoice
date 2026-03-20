# ASR Worker Process Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the single-process ASR architecture into main process + persistent ASR worker subprocess, reducing idle memory from ~700MB to ~150-200MB while hiding model load latency behind recording time.

**Architecture:** Main process handles hotkeys, recording, menu bar, history, and settings. A persistent worker subprocess manages model loading and transcription via JSON-over-stdio IPC. The worker stays alive but only loads the model on demand, unloading it after a configurable TTL (180s). Audio is passed via temporary .wav files. A unified state machine in `WorkerManager` tracks both `app_state` and `worker_state`, with a single `threading.Lock` protecting state reads/writes only — all I/O and side effects happen outside the lock.

**Tech Stack:** Python 3.11+, MLX, mlx-qwen3-asr, rumps, sounddevice, subprocess, threading

---

## Design Reference

The full state machine design was finalized in a multi-round review. Key invariants:

1. **State dimensions:** `app_state` (idle|recording|processing|done|loading) × `worker_state` (dead|starting|unloaded|loading|ready|transcribing)
2. **Lock discipline:** Lock only guards state reads/writes. Subprocess I/O, recorder, clipboard, wav writing, timers, and all callbacks execute outside the lock.
3. **Worker generation:** Every `_respawn_worker()` increments `worker_gen`. All worker events (messages, EOF) are tagged with gen and silently discarded if stale.
4. **Job lifecycle:** `pending_job` (waiting for model) → `active_job` (transcribe_file sent) → `None` (done/error). On worker death, `active_job` demotes back to `pending_job`.
5. **job_id validation:** `transcribe_done`/`transcribe_error` must match `active_job.job_id`; mismatches are discarded.
6. **TTL timer:** Only fires `unload_model` if `worker_state == ready` AND `app_state == idle` at expiry time.
7. **Quantization:** `desired_quantization` updated lazily. `loaded_quantization` tracked from `model_ready` events. Mismatch triggers reload only on next `ensure_loaded`.
8. **No preemption:** Quantization changes during `loading` or `transcribing` are deferred.

### IPC Protocol

Main → Worker (JSON Lines on stdin):
```
{"type":"ensure_loaded","quantization":"4bit"}
{"type":"transcribe_file","job_id":"abc","wav_path":"/tmp/abc.wav","sample_rate":16000,"context":"..."}
{"type":"unload_model"}
{"type":"shutdown"}
```

Worker → Main (JSON Lines on stdout):
```
{"type":"worker_ready"}
{"type":"model_loading","quantization":"4bit"}
{"type":"model_ready","quantization":"4bit"}
{"type":"transcribe_done","job_id":"abc","text":"...","language":"zh","duration_seconds":2.5}
{"type":"transcribe_error","job_id":"abc","message":"..."}
{"type":"model_unloaded"}
```

---

## File Structure

**New files:**
| File | Responsibility |
|---|---|
| `src/ohmyvoice/worker.py` | Worker subprocess entry point. Reads JSON from stdin, dispatches to ASREngine, writes JSON to stdout. ~90 lines. |
| `src/ohmyvoice/worker_manager.py` | Main process component. Subprocess lifecycle, IPC, state machine, job lifecycle, TTL/done timers, generation tracking. ~280 lines. |
| `tests/test_worker.py` | Worker unit tests with mock engine. |
| `tests/test_worker_manager.py` | State machine unit tests. |

**Modified files:**
| File | Change |
|---|---|
| `src/ohmyvoice/asr.py` | Add `quantize_bits` property, improve `unload()` to gc + clear MLX cache. |
| `src/ohmyvoice/app.py` | Replace `ASREngine` with `WorkerManager`, simplify hotkey handlers, add result/error/state callbacks. |
| `src/ohmyvoice/ui_bridge.py` | Update `_build_state_message` and `_handle_reload_model` to use manager instead of engine. |
| `src/ohmyvoice/__main__.py` | Add `--worker` flag for frozen-app subprocess spawning. |

---

## Task 1: ASR Engine — Quantization Tracking & Unload Improvement

**Files:**
- Modify: `src/ohmyvoice/asr.py:62-121`
- Test: `tests/test_asr.py`

- [ ] **Step 1: Write failing tests for quantize_bits tracking**

```python
# tests/test_asr.py — append after existing tests

def test_quantize_bits_none_before_load():
    e = ASREngine()
    assert e.quantize_bits is None


def test_quantize_bits_set_after_load(engine):
    assert engine.quantize_bits == 4


def test_quantize_bits_none_after_unload():
    e = ASREngine()
    # Unload without loading should be safe
    e.unload()
    assert e.quantize_bits is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/test_asr.py::test_quantize_bits_none_before_load -v`
Expected: FAIL — `ASREngine` has no `quantize_bits` attribute.

- [ ] **Step 3: Implement quantize_bits tracking and improved unload**

In `src/ohmyvoice/asr.py`:

Add `self._quantize_bits: int | None = None` to `__init__` (after line 65).

Add property after `is_loaded` (after line 94):
```python
@property
def quantize_bits(self) -> int | None:
    return self._quantize_bits
```

Set `self._quantize_bits = quantize_bits` at end of `load()` (before `self._session = Session(model=model)`, line 90).

Replace `unload()` (lines 119-120) with:
```python
def unload(self) -> None:
    self._session = None
    self._quantize_bits = None
    import gc
    gc.collect()
    try:
        import mlx.core as mx
        # Clear MLX Metal buffer cache to actually release GPU memory.
        # If clear_cache doesn't exist, force-flush by setting limit to 0 then restoring.
        if hasattr(mx.metal, "clear_cache"):
            mx.metal.clear_cache()
        else:
            old_limit = mx.metal.set_cache_limit(0)
            mx.metal.set_cache_limit(old_limit)
    except (ImportError, AttributeError):
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/test_asr.py -v`
Expected: All pass (including existing tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/fg/work/oss/ohmyvoice-app
git add src/ohmyvoice/asr.py tests/test_asr.py
git commit -m "feat(asr): track quantize_bits, improve unload to release MLX memory"
```

---

## Task 2: Worker Subprocess

**Files:**
- Create: `src/ohmyvoice/worker.py`
- Create: `tests/test_worker.py`

- [ ] **Step 1: Write failing tests for worker message handling**

```python
# tests/test_worker.py
import json
from io import StringIO
from unittest.mock import MagicMock, PropertyMock

import numpy as np
import pytest

from ohmyvoice.worker import ASRWorker


def _make_worker(engine=None):
    """Create a worker with mock engine and captured stdout."""
    if engine is None:
        engine = MagicMock()
        engine.is_loaded = False
        engine.quantize_bits = None
    stdout = StringIO()
    worker = ASRWorker(engine=engine, stdout=stdout)
    return worker, stdout


def _messages(stdout):
    """Parse all JSON messages from captured stdout."""
    stdout.seek(0)
    return [json.loads(line) for line in stdout if line.strip()]


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
        import wave
        # Write a valid wav file
        wav_path = str(tmp_path / "test.wav")
        audio = np.zeros(16000, dtype=np.float32)
        audio_int16 = (audio * 32767).astype(np.int16)
        with wave.open(wav_path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            f.writeframes(audio_int16.tobytes())

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

    def test_error(self):
        engine = MagicMock()
        engine.transcribe.side_effect = RuntimeError("boom")

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


class TestUnloadModel:
    def test_sends_model_unloaded(self):
        worker, stdout = _make_worker()
        worker._dispatch({"type": "unload_model"})

        worker._engine.unload.assert_called_once()
        msgs = _messages(stdout)
        assert msgs[0]["type"] == "model_unloaded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/test_worker.py -v`
Expected: FAIL — `ohmyvoice.worker` does not exist.

- [ ] **Step 3: Implement worker.py**

```python
# src/ohmyvoice/worker.py
"""ASR worker subprocess — communicates via JSON-over-stdio."""

import json
import os
import sys
import wave

import numpy as np

from ohmyvoice.asr import ASREngine


class ASRWorker:
    def __init__(self, engine=None, stdin=None, stdout=None):
        self._engine = engine or ASREngine()
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout

    def run(self):
        self._send({"type": "worker_ready"})
        for line in self._stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                self._dispatch(msg)
            except json.JSONDecodeError:
                self._send({"type": "worker_error", "message": f"invalid JSON: {line!r}"})
            except SystemExit:
                raise
            except Exception as e:
                self._send({"type": "worker_error", "message": str(e)})

    def _dispatch(self, msg):
        msg_type = msg.get("type")
        if msg_type == "ensure_loaded":
            self._ensure_loaded(msg)
        elif msg_type == "transcribe_file":
            self._transcribe_file(msg)
        elif msg_type == "unload_model":
            self._unload_model()
        elif msg_type == "shutdown":
            sys.exit(0)
        else:
            self._send({"type": "worker_error", "message": f"unknown type: {msg_type}"})

    def _ensure_loaded(self, msg):
        quantization = msg["quantization"]
        bits = int(quantization.replace("bit", ""))

        if self._engine.is_loaded and self._engine.quantize_bits == bits:
            self._send({"type": "model_ready", "quantization": quantization})
            return

        if self._engine.is_loaded:
            self._engine.unload()

        self._send({"type": "model_loading", "quantization": quantization})
        self._engine.load(quantize_bits=bits)
        self._send({"type": "model_ready", "quantization": quantization})

    def _transcribe_file(self, msg):
        job_id = msg["job_id"]
        wav_path = msg.get("wav_path", "")
        try:
            audio, file_sr = self._read_wav(wav_path)
            sample_rate = msg.get("sample_rate", file_sr)
            context = msg.get("context", "")
            result = self._engine.transcribe(audio, context=context, sample_rate=sample_rate)
            self._send({
                "type": "transcribe_done",
                "job_id": job_id,
                "text": result.text,
                "language": result.language,
                "duration_seconds": result.duration_seconds,
            })
        except Exception as e:
            self._send({
                "type": "transcribe_error",
                "job_id": job_id,
                "message": str(e),
            })
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    def _unload_model(self):
        self._engine.unload()
        self._send({"type": "model_unloaded"})

    @staticmethod
    def _read_wav(path):
        with wave.open(path, "rb") as f:
            sr = f.getframerate()
            frames = f.readframes(f.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
        return audio, sr

    def _send(self, msg):
        self._stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self._stdout.flush()


def main():
    ASRWorker().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/test_worker.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/fg/work/oss/ohmyvoice-app
git add src/ohmyvoice/worker.py tests/test_worker.py
git commit -m "feat: add ASR worker subprocess with JSON-over-stdio IPC"
```

---

## Task 3: Worker Manager — State Machine & Subprocess Lifecycle

**Files:**
- Create: `src/ohmyvoice/worker_manager.py`
- Create: `tests/test_worker_manager.py`

This is the largest component. Tests exercise the state machine by setting up state directly and calling event handlers, with a mock subprocess.

- [ ] **Step 1: Write failing tests for core state transitions**

```python
# tests/test_worker_manager.py
import json
import os
import time
import wave
from unittest.mock import MagicMock, patch

import numpy as np
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

        # Verify ensure_loaded was sent (via _send to mock stdin)
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


class TestOnRelease:
    def test_ready_sends_transcribe(self, tmp_path):
        m = _make_manager()
        m._app_state = "recording"
        m._worker_state = "ready"
        m._loaded_quantization = "4bit"
        m._desired_quantization = "4bit"

        wav_path = str(tmp_path / "test.wav")
        open(wav_path, "w").close()  # dummy file

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
        m = _make_manager()
        m._app_state = "recording"

        m.on_short_audio()

        assert m._app_state == "idle"


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

        m._on_worker_ready(1)  # stale gen

        assert m._worker_state == "starting"  # unchanged


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
        m._ttl_timer.cancel()  # cleanup

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

        assert m._active_job is not None  # unchanged
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

        m._on_transcribe_done(1, {  # gen=1, current=2
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

        assert m._worker_state == "dead"  # set before respawn
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

        assert m._worker_state == "dead"  # set to dead, respawn resets to starting


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/test_worker_manager.py -v`
Expected: FAIL — `ohmyvoice.worker_manager` does not exist.

- [ ] **Step 3: Implement worker_manager.py**

```python
# src/ohmyvoice/worker_manager.py
"""Worker process manager — subprocess lifecycle, IPC, and state machine."""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass
class PendingJob:
    job_id: str
    wav_path: str
    sample_rate: int
    context: str
    created_at: float


class WorkerManager:
    """Manages the ASR worker subprocess and transcription pipeline.

    Thread safety: self._lock guards state reads/writes only.
    All I/O (subprocess, timers, callbacks) happens outside the lock.
    """

    def __init__(
        self,
        on_result: Callable[[str, str, float], None],
        on_error: Callable[[str], None],
        on_state_change: Callable[[str], None],
        on_model_loaded: Callable[[str], None] | None = None,
        ttl_seconds: float = 180.0,
    ):
        self._on_result = on_result
        self._on_error = on_error
        self._on_state_change = on_state_change
        self._on_model_loaded = on_model_loaded
        self._ttl_seconds = ttl_seconds

        self._lock = threading.Lock()
        self._app_state = "loading"
        self._worker_state = "dead"
        self._worker_gen = 0
        self._proc: subprocess.Popen | None = None
        self._pending_job: PendingJob | None = None
        self._active_job: PendingJob | None = None
        self._desired_quantization = "4bit"
        self._loaded_quantization: str | None = None
        self._ttl_timer: threading.Timer | None = None
        self._done_timer: threading.Timer | None = None

    # --- Properties ---

    @property
    def app_state(self) -> str:
        return self._app_state

    @property
    def worker_state(self) -> str:
        return self._worker_state

    @property
    def loaded_quantization(self) -> str | None:
        return self._loaded_quantization

    # --- Public API ---

    def start(self, quantization: str = "4bit"):
        """Spawn worker and begin initial model loading."""
        self._desired_quantization = quantization
        gen = self._respawn_worker()
        self._send(gen, {"type": "ensure_loaded", "quantization": quantization})

    def on_press(self, desired_quantization: str) -> bool:
        """Handle hotkey press. Returns True if recording should start."""
        with self._lock:
            if self._app_state != "idle":
                return False
            self._app_state = "recording"
            self._desired_quantization = desired_quantization
            self._cancel_ttl_locked()

            need_respawn = self._worker_state == "dead"
            need_ensure = self._worker_state in ("dead", "starting", "unloaded")
            q_mismatch = (
                self._worker_state == "ready"
                and self._loaded_quantization != desired_quantization
            )
            gen = self._worker_gen

        # Side effects outside lock
        if need_respawn:
            gen = self._respawn_worker()
        if need_ensure or q_mismatch:
            self._send(gen, {"type": "ensure_loaded", "quantization": desired_quantization})
        return True

    def on_release(self, wav_path: str, sample_rate: int, context: str):
        """Handle hotkey release with valid audio."""
        job = PendingJob(
            job_id=uuid.uuid4().hex[:8],
            wav_path=wav_path,
            sample_rate=sample_rate,
            context=context,
            created_at=time.time(),
        )

        need_respawn = False
        send_ensure = False
        send_now = False

        with self._lock:
            if self._app_state != "recording":
                return
            self._app_state = "processing"

            if (
                self._worker_state == "ready"
                and self._loaded_quantization == self._desired_quantization
            ):
                self._active_job = job
                self._worker_state = "transcribing"
                send_now = True
            elif self._worker_state == "ready":
                # Quantization mismatch
                self._pending_job = job
                send_ensure = True
            elif self._worker_state == "dead":
                self._pending_job = job
                need_respawn = True
                send_ensure = True
            else:
                # starting, unloaded, loading — ensure_loaded already sent on press
                self._pending_job = job

            gen = self._worker_gen

        # Side effects outside lock
        if need_respawn:
            gen = self._respawn_worker()
        if send_ensure:
            self._send(gen, {"type": "ensure_loaded", "quantization": self._desired_quantization})
        if send_now:
            self._send(gen, {
                "type": "transcribe_file",
                "job_id": job.job_id,
                "wav_path": job.wav_path,
                "sample_rate": job.sample_rate,
                "context": job.context,
            })

    def on_short_audio(self):
        """Handle hotkey release with audio too short to transcribe."""
        with self._lock:
            if self._app_state != "recording":
                return
            self._app_state = "idle"
        self._on_state_change("idle")

    def reload_model(self, quantization: str):
        """Request model reload with new quantization (called from UI bridge)."""
        self._desired_quantization = quantization
        with self._lock:
            if self._worker_state in ("ready", "unloaded"):
                gen = self._worker_gen
                do_send = True
            else:
                do_send = False

        if do_send:
            self._send(gen, {"type": "ensure_loaded", "quantization": quantization})

    def shutdown(self, timeout: float = 2.0):
        """Graceful shutdown."""
        with self._lock:
            self._cancel_ttl_locked()
            self._cancel_done_timer_locked()
            gen = self._worker_gen

        self._send(gen, {"type": "shutdown"})
        if self._proc:
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()

    # --- Subprocess management ---

    def _respawn_worker(self) -> int:
        """Spawn a new worker process. Returns new generation."""
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=1)
            except Exception:
                pass

        cmd = self._worker_command()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        with self._lock:
            self._worker_gen += 1
            self._worker_state = "starting"
            self._loaded_quantization = None
            self._proc = proc
            gen = self._worker_gen

        threading.Thread(
            target=self._read_loop, args=(proc.stdout, gen), daemon=True
        ).start()
        return gen

    @staticmethod
    def _worker_command() -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "--worker"]
        return [sys.executable, "-m", "ohmyvoice.worker"]

    def _send(self, gen: int, msg: dict) -> bool:
        """Send a message to the worker. No-op if gen is stale."""
        with self._lock:
            if gen != self._worker_gen:
                return False
            proc = self._proc

        if proc is None or proc.poll() is not None:
            return False
        try:
            proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def _read_loop(self, stdout, gen: int):
        """Read JSON lines from worker stdout. Runs in dedicated thread."""
        try:
            for line in stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                with self._lock:
                    if gen != self._worker_gen:
                        return
                self._handle_worker_message(gen, msg)
        except Exception:
            pass
        finally:
            self._handle_worker_died(gen)

    # --- Worker event handlers ---

    def _handle_worker_message(self, gen: int, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "worker_ready":
            self._on_worker_ready(gen)
        elif msg_type == "model_loading":
            self._on_model_loading(gen, msg)
        elif msg_type == "model_ready":
            self._on_model_ready(gen, msg)
        elif msg_type == "transcribe_done":
            self._on_transcribe_done(gen, msg)
        elif msg_type == "transcribe_error":
            self._on_transcribe_error(gen, msg)
        elif msg_type == "model_unloaded":
            self._on_model_unloaded(gen)

    def _on_worker_ready(self, gen: int):
        with self._lock:
            if gen != self._worker_gen:
                return
            if self._worker_state == "starting":
                self._worker_state = "unloaded"

    def _on_model_loading(self, gen: int, msg: dict):
        with self._lock:
            if gen != self._worker_gen:
                return
            self._worker_state = "loading"

    def _on_model_ready(self, gen: int, msg: dict):
        quantization = msg.get("quantization")

        has_pending = False
        start_ttl = False
        initial_load_done = False
        job = None

        with self._lock:
            if gen != self._worker_gen:
                return
            self._worker_state = "ready"
            self._loaded_quantization = quantization

            if self._pending_job:
                job = self._pending_job
                self._pending_job = None
                self._active_job = job
                self._worker_state = "transcribing"
                has_pending = True
            elif self._app_state == "recording":
                pass  # RELEASE will handle it
            elif self._app_state == "loading":
                self._app_state = "idle"
                initial_load_done = True
            else:
                start_ttl = True

            cur_gen = self._worker_gen

        # Side effects outside lock
        if has_pending:
            self._send(cur_gen, {
                "type": "transcribe_file",
                "job_id": job.job_id,
                "wav_path": job.wav_path,
                "sample_rate": job.sample_rate,
                "context": job.context,
            })
        if start_ttl:
            self._start_ttl()
        if initial_load_done:
            self._on_state_change("idle")
        if self._on_model_loaded:
            self._on_model_loaded(quantization)

    def _on_transcribe_done(self, gen: int, msg: dict):
        with self._lock:
            if gen != self._worker_gen:
                return
            if not self._active_job or msg.get("job_id") != self._active_job.job_id:
                return
            self._active_job = None
            self._worker_state = "ready"
            self._app_state = "done"

        text = msg.get("text", "")
        language = msg.get("language", "")
        duration = msg.get("duration_seconds", 0.0)
        self._on_result(text, language, duration)
        self._on_state_change("done")
        self._start_ttl()
        self._start_done_timer()

    def _on_transcribe_error(self, gen: int, msg: dict):
        with self._lock:
            if gen != self._worker_gen:
                return
            if not self._active_job or msg.get("job_id") != self._active_job.job_id:
                return
            self._active_job = None
            self._worker_state = "ready"
            self._app_state = "idle"

        self._on_error(msg.get("message", "Unknown error"))
        self._on_state_change("idle")
        self._start_ttl()

    def _on_model_unloaded(self, gen: int):
        with self._lock:
            if gen != self._worker_gen:
                return
            self._worker_state = "unloaded"
            self._loaded_quantization = None

    def _handle_worker_died(self, gen: int):
        need_respawn = False
        with self._lock:
            if gen != self._worker_gen:
                return
            self._worker_state = "dead"
            self._loaded_quantization = None
            self._cancel_ttl_locked()

            if self._active_job:
                self._pending_job = self._active_job
                self._active_job = None

            if self._app_state in ("recording", "processing", "loading"):
                need_respawn = True

        if need_respawn:
            new_gen = self._respawn_worker()
            self._send(new_gen, {"type": "ensure_loaded", "quantization": self._desired_quantization})

    # --- Timers ---

    def _start_ttl(self):
        with self._lock:
            self._cancel_ttl_locked()
            self._ttl_timer = threading.Timer(self._ttl_seconds, self._on_ttl_expired)
            self._ttl_timer.daemon = True
            self._ttl_timer.start()

    def _on_ttl_expired(self):
        with self._lock:
            if self._worker_state != "ready" or self._app_state != "idle":
                return
            gen = self._worker_gen
        self._send(gen, {"type": "unload_model"})

    def _start_done_timer(self):
        with self._lock:
            self._cancel_done_timer_locked()
            self._done_timer = threading.Timer(1.0, self._on_done_timer_expired)
            self._done_timer.daemon = True
            self._done_timer.start()

    def _on_done_timer_expired(self):
        with self._lock:
            if self._app_state != "done":
                return
            self._app_state = "idle"
        self._on_state_change("idle")

    def _cancel_ttl_locked(self):
        if self._ttl_timer:
            self._ttl_timer.cancel()
            self._ttl_timer = None

    def _cancel_done_timer_locked(self):
        if self._done_timer:
            self._done_timer.cancel()
            self._done_timer = None

    # --- Wav utilities ---

    @staticmethod
    def write_temp_wav(audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Write float32 mono audio to a temp wav file. Returns path."""
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="ohmyvoice-")
        os.close(fd)
        audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        with wave.open(path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sample_rate)
            f.writeframes(audio_int16.tobytes())
        return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/test_worker_manager.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/fg/work/oss/ohmyvoice-app
git add src/ohmyvoice/worker_manager.py tests/test_worker_manager.py
git commit -m "feat: add WorkerManager with state machine, IPC, job lifecycle"
```

---

## Task 4: App & UIBridge Integration

**Files:**
- Modify: `src/ohmyvoice/app.py`
- Modify: `src/ohmyvoice/ui_bridge.py:145-190`
- Modify: `src/ohmyvoice/__main__.py`

- [ ] **Step 1: Update `__main__.py` for worker subprocess support**

Replace the contents of `src/ohmyvoice/__main__.py` with:

```python
import sys


def main():
    if "--worker" in sys.argv:
        from ohmyvoice.worker import main as worker_main
        worker_main()
    else:
        from ohmyvoice.app import main as app_main
        app_main()


main()
```

- [ ] **Step 2: Run existing tests to verify nothing breaks**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/ -v --ignore=tests/test_asr.py`
Expected: All pass (skip test_asr.py since it loads the real model).

- [ ] **Step 3: Rewrite app.py to use WorkerManager**

Replace `src/ohmyvoice/app.py` with the following (preserving `_clean_text`, `_load_status_icon`, and icon logic exactly):

Key changes:
- Remove `from ohmyvoice.asr import ASREngine`
- Add `from ohmyvoice.worker_manager import WorkerManager`
- Replace `self._engine = ASREngine()` with `self._manager = WorkerManager(...)`
- Replace `self._load_model_async()` with `self._start_worker(); self._start_hotkey()`
- Simplify `_on_hotkey_press` / `_on_hotkey_release` to delegate to manager
- Remove `_process_audio` — replaced by manager callbacks
- Add `_handle_result`, `_handle_error`, `_handle_state_change`
- Replace `sleep(1)` done transition with manager's done_timer

The full replacement for `OhMyVoiceApp.__init__` through end of class:

```python
class OhMyVoiceApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="OhMyVoice",
            icon=None,
            template=True,
            quit_button=None,
        )
        self._set_icon("mic_idle.png", template=True)
        self._settings = Settings()
        self._history = HistoryDB()
        self._recorder = Recorder(
            sample_rate=16000, device=self._settings.input_device
        )
        self._manager = WorkerManager(
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_state_change=self._handle_state_change,
            on_model_loaded=self._handle_model_loaded,
        )
        self._hotkey: HotkeyManager | None = None
        self._ui_bridge = UIBridge(self)
        self._build_menu()
        self._start_hotkey()
        self._manager.start(quantization=self._settings.model_quantization)

    def _build_menu(self):
        self.menu = [
            rumps.MenuItem("状态: 加载中...", callback=None),
            None,
            rumps.MenuItem("最近转写", callback=None),
            None,
            rumps.MenuItem("设置...", callback=self._on_settings),
            rumps.MenuItem("全部历史", callback=self._on_history),
            None,
            rumps.MenuItem("退出", callback=self._on_quit),
        ]

    def _start_hotkey(self):
        self._hotkey = HotkeyManager(
            modifiers=self._settings.hotkey_modifiers,
            key=self._settings.hotkey_key,
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
        )
        ok = self._hotkey.start()
        if not ok:
            self.menu["状态: 加载中..."].title = "需要辅助功能权限"

    def _on_hotkey_press(self):
        q = self._settings.model_quantization
        if not self._manager.on_press(q):
            return
        if self._settings.sound_feedback:
            play_start()
        self._recorder.start()

    def _on_hotkey_release(self):
        if self._manager.app_state != "recording":
            return
        audio = self._recorder.stop()
        if len(audio) < 1600:
            print("[DEBUG] Audio too short, ignoring")
            self._manager.on_short_audio()
            return
        wav_path = WorkerManager.write_temp_wav(audio)
        context = self._settings.get_active_prompt()
        self._manager.on_release(wav_path, 16000, context)

    def _handle_result(self, text, language, duration_seconds):
        text = _clean_text(text)
        if text:
            copy_to_clipboard(text)
            self._history.add(text, duration=duration_seconds)
            self._history.prune(self._settings.history_max_entries)
            self._update_recent_menu()
            if self._settings.sound_feedback:
                play_done()
            if self._settings.notification_on_complete:
                send_notification(text)

    def _handle_error(self, message):
        print(f"ASR error: {message}")

    def _handle_state_change(self, new_state):
        self._set_state(new_state)

    def _handle_model_loaded(self, quantization):
        # Update status menu on first successful load
        try:
            item = self.menu["状态: 加载中..."]
            item.title = f"就绪 · {self._settings.hotkey_display}"
        except KeyError:
            pass
        # Notify UI bridge if running
        if self._ui_bridge.is_running:
            self._ui_bridge._send({"type": "model_reloaded", "success": True})

    def _set_state(self, state: str):
        icon_map = {
            "idle": ("mic_idle.png", True),
            "recording": ("mic_recording.png", False),
            "processing": ("mic_processing.png", False),
            "done": ("mic_done.png", False),
        }
        icon_name, template = icon_map.get(state, ("mic_idle.png", True))
        self._set_icon(icon_name, template)

    def _set_icon(self, icon_name: str, template: bool):
        self._icon = str(_ICONS / icon_name)
        self._template = template
        self._icon_nsimage = _load_status_icon(icon_name, template)
        if hasattr(self, "_nsapp"):
            self._nsapp.setStatusBarIcon()

    def _update_recent_menu(self):
        try:
            records = self._history.recent(3)
            sub = self.menu["最近转写"]
            for key in list(sub.keys()):
                del sub[key]
            for r in records:
                preview = r["text"][:40] + ("…" if len(r["text"]) > 40 else "")
                sub[preview] = rumps.MenuItem(
                    preview,
                    callback=lambda _, text=r["text"]: copy_to_clipboard(text),
                )
        except Exception:
            pass

    def _on_settings(self, _):
        self._ui_bridge.open_preferences()

    def _on_history(self, _):
        self._ui_bridge.open_history()

    def _on_quit(self, _):
        if self._hotkey:
            self._hotkey.stop()
        self._manager.shutdown()
        self._history.close()
        rumps.quit_application()
```

Also update the imports at the top of app.py — replace `from ohmyvoice.asr import ASREngine` with `from ohmyvoice.worker_manager import WorkerManager`.

- [ ] **Step 4: Update ui_bridge.py references**

In `src/ohmyvoice/ui_bridge.py`, update `_build_state_message` (line 162):

Replace:
```python
"model_loaded": getattr(self._app._engine, "is_loaded", False),
```
With:
```python
"model_loaded": self._app._manager.worker_state in ("ready", "transcribing"),
```

Update `_handle_reload_model` (lines 170-190) — replace the entire method:
```python
def _handle_reload_model(self, msg):
    quantization = msg.get("quantization", "4bit")
    self._app._settings.model_quantization = quantization
    self._send({"type": "model_reloading"})
    self._app._manager.reload_model(quantization)
```

- [ ] **Step 5: Update test_ui_bridge.py**

In `tests/test_ui_bridge.py`, update `test_build_state_message` — replace the mock setup:

```python
def test_build_state_message():
    app = MagicMock()
    app._settings.model_name = "Qwen3-ASR-0.6B"
    app._settings.model_quantization = "4bit"
    app._manager.worker_state = "ready"
    # ...rest stays the same
```

- [ ] **Step 6: Run all tests**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/ -v --ignore=tests/test_asr.py`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/fg/work/oss/ohmyvoice-app
git add src/ohmyvoice/app.py src/ohmyvoice/ui_bridge.py src/ohmyvoice/__main__.py tests/test_ui_bridge.py
git commit -m "feat: integrate WorkerManager into app, replace direct ASREngine usage"
```

---

## Task 5: End-to-End Verification

**Files:** None (manual verification)

- [ ] **Step 1: Run full test suite including ASR tests**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m pytest tests/ -v`
Expected: All pass. The `test_asr.py` tests still work because ASREngine API is unchanged.

- [ ] **Step 2: Verify worker subprocess starts correctly**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && echo '{"type":"shutdown"}' | python -m ohmyvoice.worker`
Expected: Outputs `{"type": "worker_ready"}` then exits.

- [ ] **Step 3: Measure worker memory baseline**

Run:
```bash
cd /Users/fg/work/oss/ohmyvoice-app
python -c "
import subprocess, sys, time, os
proc = subprocess.Popen([sys.executable, '-m', 'ohmyvoice.worker'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
line = proc.stdout.readline()
print('Worker ready:', line.strip())
time.sleep(2)
# Check RSS
pid = proc.pid
rss = int(os.popen(f'ps -o rss= -p {pid}').read().strip())
print(f'Worker RSS (empty): {rss / 1024:.1f} MB')
proc.stdin.write('{\"type\":\"shutdown\"}\n')
proc.stdin.flush()
proc.wait()
"
```
Expected: Worker RSS ~50-60 MB (imports only, no model loaded).

- [ ] **Step 4: Launch the app and test recording flow**

Run: `cd /Users/fg/work/oss/ohmyvoice-app && python -m ohmyvoice`

Manual test checklist:
1. App appears in menu bar with loading icon
2. Status changes to "就绪" after model loads (~500ms)
3. Press Option+Space → recording icon → speak → release → text copied to clipboard
4. Check Activity Monitor: after TTL (180s), worker RSS should drop to ~50-60 MB
5. Press Option+Space again → brief delay while model reloads → transcription works

- [ ] **Step 5: Verify idle memory**

After TTL has fired (3 min idle), check total memory:
- Main Python process: expected ~80-120 MB
- Worker process: expected ~50-60 MB
- Total idle: expected ~150-200 MB (down from ~700 MB)

- [ ] **Step 6: Final commit if any adjustments were needed**

```bash
cd /Users/fg/work/oss/ohmyvoice-app
git add -A
git commit -m "fix: adjustments from end-to-end verification"
```
