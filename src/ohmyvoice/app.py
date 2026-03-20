import re

import rumps
from AppKit import NSImage, NSImageRep


_FILLER_WORDS = r'(?:呃|嗯|啊|哦|额|唔|那个|就是说|然后吧)+'


def _clean_text(text: str) -> str:
    """Remove filler words and clean up punctuation artifacts."""
    # Remove fillers optionally surrounded by punctuation
    text = re.sub(rf'[，、。]*{_FILLER_WORDS}[，、。]*', '，', text)
    # Collapse repeated punctuation
    text = re.sub(r'[，、。]{2,}', '，', text)
    # Strip leading/trailing punctuation
    text = re.sub(r'^[，、。\s]+|[，、\s]+$', '', text)
    return text.strip()

from ohmyvoice.audio_feedback import play_done, play_start
from ohmyvoice.clipboard import copy_to_clipboard
from ohmyvoice.history import HistoryDB
from ohmyvoice.hotkey import HotkeyManager
from ohmyvoice.notification import send_notification
from ohmyvoice.recorder import Recorder
from ohmyvoice.settings import Settings
from ohmyvoice.ui_bridge import UIBridge
from ohmyvoice.worker_manager import WorkerManager

from ohmyvoice.paths import get_resources_dir
_ICONS = get_resources_dir() / "icons"
_ICON_POINT_SIZE = (18, 18)


def _load_status_icon(icon_name: str, template: bool) -> NSImage:
    """Build a status bar icon with 1x and 2x image reps."""
    image = NSImage.alloc().initWithSize_(_ICON_POINT_SIZE)
    base_path = _ICONS / icon_name
    retina_path = base_path.with_name(f"{base_path.stem}@2x{base_path.suffix}")

    for path in (base_path, retina_path):
        if not path.exists():
            continue
        rep = NSImageRep.imageRepWithContentsOfFile_(str(path))
        if rep is None:
            continue
        rep.setSize_(_ICON_POINT_SIZE)
        image.addRepresentation_(rep)

    image.setTemplate_(template)
    return image


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
        # Update icon directly (reviewer fix #8: manager doesn't fire state_change for recording)
        self._set_state("recording")
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
        # Update icon directly (reviewer fix #8)
        self._set_state("processing")
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
        """Called by manager for done->idle and error->idle transitions."""
        self._set_state(new_state)

    def _handle_model_loaded(self, quantization):
        try:
            item = self.menu["状态: 加载中..."]
            item.title = f"就绪 · {self._settings.hotkey_display}"
        except KeyError:
            pass
        if self._ui_bridge.is_running:
            self._ui_bridge.notify_model_reloaded()

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
            # Remove old items (sub.clear() crashes when no submenu exists)
            for key in list(sub.keys()):
                del sub[key]
            for r in records:
                preview = r["text"][:40] + ("…" if len(r["text"]) > 40 else "")
                sub[preview] = rumps.MenuItem(
                    preview,
                    callback=lambda _, text=r["text"]: copy_to_clipboard(text),
                )
        except Exception:
            pass  # non-critical: menu display only

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


def main():
    OhMyVoiceApp().run()


if __name__ == "__main__":
    main()
