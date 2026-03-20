import json
from pathlib import Path

_PROMPT_VERSION = 2

_DEFAULTS = {
    "hotkey": {"modifiers": ["option"], "key": "space"},
    "audio": {
        "input_device": None,
        "sound_feedback": True,
        "max_recording_seconds": 60,
    },
    "model": {
        "name": "Qwen3-ASR-0.6B",
        "quantization": "4bit",
        "path": "~/.cache/ohmyvoice/models/",
    },
    "prompt": {
        "active_template": "coding",
        "custom_prompt": "",
        "templates": {
            "coding": "这是一位程序员对 coding agent 的口述指令。常见术语：Claude Anthropic OpenAI GitHub Copilot React TypeScript Python API endpoint component async await Docker Kubernetes Ubuntu macOS Homebrew npm pip PostgreSQL Redis Nginx Vercel Cloudflare AWS 阿里云 Tencent",
            "meeting": "这是一段会议讨论录音，可能涉及多人发言。",
            "general": "",
        },
    },
    "language": "auto",
    "autostart": False,
    "notification_on_complete": False,
    "history_max_entries": 1000,
    "prompt_version": 0,
}


class Settings:
    def __init__(self, config_dir: Path | None = None):
        if config_dir is None:
            config_dir = Path.home() / ".config" / "ohmyvoice"
        self._path = config_dir / "settings.json"
        self._data = _deep_copy(_DEFAULTS)
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path) as f:
                    saved = json.load(f)
                _deep_merge(self._data, saved)
            except (json.JSONDecodeError, OSError):
                self._data = _deep_copy(_DEFAULTS)
        if self._data.get("prompt_version", 0) < _PROMPT_VERSION:
            self._data["prompt"]["templates"] = _deep_copy(
                _DEFAULTS["prompt"]["templates"]
            )
            self._data["prompt_version"] = _PROMPT_VERSION
            self.save()

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    @property
    def path(self) -> Path:
        return self._path

    def reload(self):
        """Re-read settings.json from disk (called after Swift UI closes)."""
        self._data = _deep_copy(_DEFAULTS)
        self._load()

    @property
    def hotkey_modifiers(self) -> list[str]:
        return self._data["hotkey"]["modifiers"]

    @hotkey_modifiers.setter
    def hotkey_modifiers(self, val: list[str]):
        self._data["hotkey"]["modifiers"] = val

    @property
    def hotkey_key(self) -> str:
        return self._data["hotkey"]["key"]

    @hotkey_key.setter
    def hotkey_key(self, val: str):
        self._data["hotkey"]["key"] = val

    @property
    def input_device(self) -> str | None:
        return self._data["audio"]["input_device"]

    @input_device.setter
    def input_device(self, val: str | None):
        self._data["audio"]["input_device"] = val

    @property
    def sound_feedback(self) -> bool:
        return self._data["audio"]["sound_feedback"]

    @sound_feedback.setter
    def sound_feedback(self, val: bool):
        self._data["audio"]["sound_feedback"] = val

    @property
    def max_recording_seconds(self) -> int:
        return self._data["audio"]["max_recording_seconds"]

    @max_recording_seconds.setter
    def max_recording_seconds(self, val: int):
        self._data["audio"]["max_recording_seconds"] = val

    @property
    def model_name(self) -> str:
        return self._data["model"]["name"]

    @property
    def model_quantization(self) -> str:
        return self._data["model"]["quantization"]

    @model_quantization.setter
    def model_quantization(self, val: str):
        self._data["model"]["quantization"] = val

    @property
    def model_path(self) -> str:
        return self._data["model"]["path"]

    @property
    def active_prompt_template(self) -> str:
        return self._data["prompt"]["active_template"]

    @active_prompt_template.setter
    def active_prompt_template(self, val: str):
        self._data["prompt"]["active_template"] = val

    @property
    def custom_prompt(self) -> str:
        return self._data["prompt"]["custom_prompt"]

    @custom_prompt.setter
    def custom_prompt(self, val: str):
        self._data["prompt"]["custom_prompt"] = val

    @property
    def prompt_templates(self) -> dict[str, str]:
        return self._data["prompt"]["templates"]

    def get_active_prompt(self) -> str:
        t = self.active_prompt_template
        if t == "custom":
            return self.custom_prompt
        return self.prompt_templates.get(t, "")

    @property
    def language(self) -> str:
        return self._data["language"]

    @language.setter
    def language(self, val: str):
        self._data["language"] = val

    @property
    def autostart(self) -> bool:
        return self._data["autostart"]

    @autostart.setter
    def autostart(self, val: bool):
        self._data["autostart"] = val

    @property
    def notification_on_complete(self) -> bool:
        return self._data["notification_on_complete"]

    @notification_on_complete.setter
    def notification_on_complete(self, val: bool):
        self._data["notification_on_complete"] = val

    @property
    def history_max_entries(self) -> int:
        return self._data["history_max_entries"]

    @history_max_entries.setter
    def history_max_entries(self, val: int):
        self._data["history_max_entries"] = val

    @property
    def hotkey_display(self) -> str:
        symbols = {"command": "⌘", "option": "⌥", "control": "⌃", "shift": "⇧"}
        mods = "".join(symbols.get(m, m) for m in self.hotkey_modifiers)
        return f"{mods}{self.hotkey_key.upper()}"


def _deep_copy(d):
    return json.loads(json.dumps(d))


def _deep_merge(base: dict, override: dict):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
