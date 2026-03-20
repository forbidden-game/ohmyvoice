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
            try:
                gen = self._respawn_worker()
            except Exception:
                with self._lock:
                    self._app_state = "idle"
                return False
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
