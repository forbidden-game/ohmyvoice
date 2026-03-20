"""Subprocess management for Swift UI."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path


class UIBridge:
    def __init__(self, app):
        self._app = app
        self._process = None
        self._reader_thread = None

    def open_preferences(self):
        self._launch(
            "preferences",
            "--settings", str(self._app._settings.path),
        )

    def open_history(self):
        self._launch(
            "history",
            "--db", str(self._app._history.db_path),
        )

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    def _launch(self, *args):
        if self.is_running:
            return  # already open
        binary = self._find_binary()
        if binary is None:
            import rumps
            rumps.alert("OhMyVoice", "UI 组件未找到，请重新安装应用。")
            return
        self._process = subprocess.Popen(
            [str(binary)] + list(args),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True
        )
        self._reader_thread.start()

    def _find_binary(self) -> Path | None:
        # 1. Environment override
        env_path = os.environ.get("OHMYVOICE_UI_PATH")
        if env_path:
            p = Path(env_path)
            if p.exists():
                return p

        # 2. App bundle (frozen): Contents/MacOS/ohmyvoice-ui
        if getattr(sys, "frozen", False):
            bundle_path = Path(sys.executable).parent / "ohmyvoice-ui"
            if bundle_path.exists():
                return bundle_path

        # 3. Development: <project>/ui/.build/release/ohmyvoice-ui
        project_root = Path(__file__).parent.parent.parent
        dev_path = project_root / "ui" / ".build" / "release" / "ohmyvoice-ui"
        if dev_path.exists():
            return dev_path

        return None

    def _read_loop(self):
        try:
            for line in self._process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._handle_message(msg)
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
        finally:
            self._on_process_exit()

    def _send(self, msg: dict):
        if not self.is_running:
            return
        try:
            self._process.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "ready":
            proto = msg.get("protocol", 0)
            if proto != 1:
                print(f"Protocol mismatch: Swift={proto}, Python=1")
            self._send(self._build_state_message())
        elif msg_type == "reload_model":
            self._handle_reload_model(msg)
        elif msg_type == "update_mic":
            self._handle_update_mic(msg)
        elif msg_type == "toggle_autostart":
            self._handle_toggle_autostart(msg)
        elif msg_type == "start_hotkey_capture":
            if self._app._hotkey:
                self._app._hotkey.pause()
            self._send({"type": "hotkey_paused"})
        elif msg_type == "finish_hotkey_capture":
            mods = msg.get("modifiers", [])
            key = msg.get("key", "")
            s = self._app._settings
            s.hotkey_modifiers = mods
            s.hotkey_key = key
            s.save()
            if self._app._hotkey:
                self._app._hotkey.update_hotkey(mods, key)
                self._app._hotkey.resume()
        elif msg_type == "cancel_hotkey_capture":
            if self._app._hotkey:
                self._app._hotkey.resume()
        elif msg_type == "clear_history":
            self._app._history.clear()
            self._send({"type": "history_cleared"})
        elif msg_type == "close":
            self._app._settings.reload()
            self._schedule_menu_update()

    def _schedule_menu_update(self):
        """Post a one-shot timer to update the recent menu on the main thread.

        Isolated here so tests can patch/skip it without importing rumps.
        """
        import rumps
        rumps.Timer(lambda t: (self._app._update_recent_menu(), t.stop()), 0).start()

    def _build_state_message(self) -> dict:
        try:
            from ohmyvoice.recorder import Recorder
            devices = Recorder.list_input_devices()
            mic_list = [{"name": d["name"]} for d in devices]
        except Exception:
            mic_list = []
        try:
            from ohmyvoice.asr import _cache_dir_for
            bits = int(self._app._settings.model_quantization.replace("bit", ""))
            cache_path = _cache_dir_for(self._app._settings.model_name, bits)
            disk_usage = _dir_size_str(cache_path)
        except Exception:
            disk_usage = "—"
        from ohmyvoice import __version__
        return {
            "type": "state",
            "model_loaded": self._app._manager.worker_state in ("ready", "transcribing"),
            "model_name": self._app._settings.model_name,
            "quantization": self._app._settings.model_quantization,
            "disk_usage": disk_usage,
            "mic_devices": mic_list,
            "version": __version__,
        }

    def _handle_reload_model(self, msg):
        quantization = msg.get("quantization", "4bit")
        # Update in-memory settings immediately (Swift already wrote settings.json)
        self._app._settings.model_quantization = quantization
        self._send({"type": "model_reloading"})
        self._app._manager.reload_model(quantization)

    def _handle_update_mic(self, msg):
        device = msg.get("device")
        self._app._settings.input_device = device
        self._app._settings.save()
        try:
            from ohmyvoice.recorder import Recorder
            self._app._recorder = Recorder(sample_rate=16000, device=device)
        except Exception:
            pass

    def _handle_toggle_autostart(self, msg):
        enabled = msg.get("enabled", False)
        self._app._settings.autostart = enabled
        self._app._settings.save()
        try:
            from ohmyvoice import autostart
            if enabled:
                autostart.enable()
            else:
                autostart.disable()
            self._send({"type": "autostart_done", "success": True})
        except Exception:
            self._send({"type": "autostart_done", "success": False})

    def notify_model_reloaded(self, success=True, error=None):
        """Notify the UI that model reload completed."""
        msg = {"type": "model_reloaded", "success": success}
        if error:
            msg["error"] = error
        self._send(msg)

    def _on_process_exit(self):
        if self._process:
            self._process.wait()  # ensure returncode is set
        exit_code = self._process.returncode if self._process else -1
        # Safety: resume hotkey if it was paused
        if self._app._hotkey:
            self._app._hotkey.resume()
        # Refresh settings from file
        self._app._settings.reload()
        self._schedule_menu_update()
        self._process = None
        if exit_code != 0:
            print(f"ohmyvoice-ui exited with code {exit_code}")


def _dir_size_str(path: Path) -> str:
    if not path.exists():
        return "—"
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    if total < 1024:
        return f"{total} B"
    if total < 1024 ** 2:
        return f"{total / 1024:.0f} KB"
    if total < 1024 ** 3:
        return f"{total / 1024 ** 2:.0f} MB"
    return f"{total / 1024 ** 3:.1f} GB"
