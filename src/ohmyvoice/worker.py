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
