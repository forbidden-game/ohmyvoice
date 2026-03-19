# OhMyVoice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS menu bar speech-to-text app using Qwen3-ASR-0.6B locally, with push-to-talk → clipboard workflow.

**Architecture:** Single-process Python app. `rumps` for menu bar UI, `PyObjC` for global hotkey / clipboard / notifications, `mlx-qwen3-asr` for ASR inference, `sounddevice` for audio capture, `sqlite3` for history. Each module has one clear responsibility and communicates through simple function calls.

**Tech Stack:** Python 3.11+, mlx-qwen3-asr, rumps, PyObjC, sounddevice, sqlite3

**Spec:** `docs/superpowers/specs/2026-03-20-ohmyvoice-design.md`

---

## File Structure

```
ohmyvoice-app/
├── pyproject.toml
├── src/
│   └── ohmyvoice/
│       ├── __init__.py
│       ├── app.py               # rumps App, ties everything together
│       ├── settings.py          # JSON settings read/write/defaults
│       ├── history.py           # SQLite CRUD for transcription records
│       ├── clipboard.py         # Write text to macOS clipboard
│       ├── audio_feedback.py    # Play system sounds
│       ├── notification.py      # macOS system notifications
│       ├── recorder.py          # sounddevice audio capture
│       ├── asr.py               # Qwen3-ASR Session wrapper
│       ├── model_manager.py     # Model download/convert/load
│       ├── hotkey.py            # CGEventTap global key monitoring
│       └── autostart.py         # Login Items (launchd plist)
├── resources/
│   ├── icons/
│   │   ├── mic_idle.png         # 22x22 template image, black+alpha
│   │   ├── mic_recording.png    # 22x22 solid red mic
│   │   ├── mic_processing.png   # 22x22 solid purple mic
│   │   └── mic_done.png         # 22x22 solid green checkmark
│   └── sounds/
│       ├── start.aiff           # recording start chime
│       └── done.aiff            # transcription complete chime
├── tests/
│   ├── __init__.py
│   ├── test_settings.py
│   ├── test_history.py
│   ├── test_clipboard.py
│   ├── test_recorder.py
│   ├── test_asr.py
│   ├── test_model_manager.py
│   └── test_autostart.py
└── .gitignore
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/ohmyvoice/__init__.py`
- Create: `.gitignore`
- Create: `resources/icons/` (placeholder)
- Create: `resources/sounds/` (placeholder)
- Create: `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ohmyvoice"
version = "0.1.0"
description = "macOS local speech-to-text menu bar app"
requires-python = ">=3.11"
dependencies = [
    "mlx-qwen3-asr[mic]>=0.2.4",
    "rumps>=0.4.0",
    "pyobjc-framework-Cocoa>=10.0",
    "pyobjc-framework-Quartz>=10.0",
    "sounddevice>=0.4.6",
    "huggingface-hub>=0.20.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
ohmyvoice = "ohmyvoice.app:main"

[tool.hatch.build.targets.wheel]
packages = ["src/ohmyvoice"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create __init__.py**

```python
# src/ohmyvoice/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
.superpowers/
.pytest_cache/
*.db
```

- [ ] **Step 4: Create placeholder directories**

```bash
mkdir -p resources/icons resources/sounds tests
touch tests/__init__.py
```

- [ ] **Step 5: Create virtual environment and install deps**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: Installation succeeds. `mlx-qwen3-asr`, `rumps`, `pyobjc` all install.

- [ ] **Step 6: Verify pytest runs**

Run: `python -m pytest tests/ -v`
Expected: "no tests ran" (0 collected), exit code 5 (no tests). No import errors.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/ tests/ resources/ .gitignore
git commit -m "feat: project scaffolding with dependencies"
```

---

## Task 2: Settings Module

**Files:**
- Create: `src/ohmyvoice/settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_settings.py
import json
from pathlib import Path

from ohmyvoice.settings import Settings


def test_defaults_when_no_file(tmp_path):
    s = Settings(config_dir=tmp_path)
    assert s.hotkey_modifiers == ["option"]
    assert s.hotkey_key == "space"
    assert s.sound_feedback is True
    assert s.language == "auto"
    assert s.autostart is False
    assert s.notification_on_complete is False
    assert s.max_recording_seconds == 60
    assert s.history_max_entries == 1000
    assert s.active_prompt_template == "coding"
    assert s.model_quantization == "4bit"


def test_save_and_reload(tmp_path):
    s = Settings(config_dir=tmp_path)
    s.hotkey_key = "r"
    s.hotkey_modifiers = ["command", "shift"]
    s.save()

    s2 = Settings(config_dir=tmp_path)
    assert s2.hotkey_key == "r"
    assert s2.hotkey_modifiers == ["command", "shift"]


def test_update_preserves_other_fields(tmp_path):
    s = Settings(config_dir=tmp_path)
    s.language = "zh"
    s.save()

    s2 = Settings(config_dir=tmp_path)
    assert s2.language == "zh"
    assert s2.sound_feedback is True  # untouched field


def test_get_active_prompt_text(tmp_path):
    s = Settings(config_dir=tmp_path)
    prompt = s.get_active_prompt()
    assert "程序员" in prompt or "coding" in prompt.lower()

    s.active_prompt_template = "custom"
    s.custom_prompt = "medical terminology"
    assert s.get_active_prompt() == "medical terminology"


def test_corrupted_file_resets_to_defaults(tmp_path):
    (tmp_path / "settings.json").write_text("not json{{{")
    s = Settings(config_dir=tmp_path)
    assert s.hotkey_key == "space"  # defaults loaded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ohmyvoice.settings'`

- [ ] **Step 3: Implement settings module**

```python
# src/ohmyvoice/settings.py
import json
from pathlib import Path

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
            "coding": "这是一位程序员对 coding agent 的口述指令。内容涉及 React、TypeScript、Python、API 设计等技术话题，包含大量英文技术术语。",
            "meeting": "这是一段会议讨论录音，可能涉及多人发言。",
            "general": "",
        },
    },
    "language": "auto",
    "autostart": False,
    "notification_on_complete": False,
    "history_max_entries": 1000,
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

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # --- Hotkey ---
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

    # --- Audio ---
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

    # --- Model ---
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

    # --- Prompt ---
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

    # --- General ---
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_settings.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/settings.py tests/test_settings.py
git commit -m "feat: settings module with JSON persistence and defaults"
```

---

## Task 3: History Module

**Files:**
- Create: `src/ohmyvoice/history.py`
- Create: `tests/test_history.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_history.py
from ohmyvoice.history import HistoryDB


def test_add_and_list(tmp_path):
    db = HistoryDB(tmp_path / "test.db")
    db.add("hello world", duration=2.5)
    db.add("second entry", duration=1.0)

    records = db.recent(10)
    assert len(records) == 2
    assert records[0]["text"] == "second entry"  # newest first
    assert records[1]["text"] == "hello world"


def test_recent_limit(tmp_path):
    db = HistoryDB(tmp_path / "test.db")
    for i in range(10):
        db.add(f"entry {i}", duration=1.0)

    records = db.recent(3)
    assert len(records) == 3
    assert records[0]["text"] == "entry 9"


def test_search(tmp_path):
    db = HistoryDB(tmp_path / "test.db")
    db.add("React Server Component", duration=2.0)
    db.add("TypeScript generics", duration=1.5)
    db.add("Python asyncio", duration=3.0)

    results = db.search("TypeScript")
    assert len(results) == 1
    assert results[0]["text"] == "TypeScript generics"


def test_prune_old_entries(tmp_path):
    db = HistoryDB(tmp_path / "test.db")
    for i in range(15):
        db.add(f"entry {i}", duration=1.0)

    db.prune(max_entries=10)
    assert len(db.recent(20)) == 10
    # Oldest entries pruned
    texts = [r["text"] for r in db.recent(20)]
    assert "entry 0" not in texts
    assert "entry 14" in texts


def test_clear(tmp_path):
    db = HistoryDB(tmp_path / "test.db")
    db.add("something", duration=1.0)
    db.clear()
    assert len(db.recent(10)) == 0


def test_get_by_id(tmp_path):
    db = HistoryDB(tmp_path / "test.db")
    db.add("find me", duration=2.0)
    records = db.recent(1)
    record = db.get(records[0]["id"])
    assert record["text"] == "find me"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_history.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement history module**

```python
# src/ohmyvoice/history.py
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_created_at ON transcriptions(created_at DESC);
"""


class HistoryDB:
    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".local" / "share" / "ohmyvoice" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def add(self, text: str, duration: float) -> int:
        cur = self._conn.execute(
            "INSERT INTO transcriptions (text, duration_seconds) VALUES (?, ?)",
            (text, duration),
        )
        self._conn.commit()
        return cur.lastrowid

    def recent(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, duration_seconds, created_at "
            "FROM transcriptions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, record_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, text, duration_seconds, created_at "
            "FROM transcriptions WHERE id = ?",
            (record_id,),
        ).fetchone()
        return dict(row) if row else None

    def search(self, query: str, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, duration_seconds, created_at "
            "FROM transcriptions WHERE text LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def prune(self, max_entries: int = 1000):
        self._conn.execute(
            "DELETE FROM transcriptions WHERE id NOT IN "
            "(SELECT id FROM transcriptions ORDER BY created_at DESC LIMIT ?)",
            (max_entries,),
        )
        self._conn.commit()

    def clear(self):
        self._conn.execute("DELETE FROM transcriptions")
        self._conn.commit()

    def close(self):
        self._conn.close()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_history.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/history.py tests/test_history.py
git commit -m "feat: history module with SQLite storage, search, and pruning"
```

---

## Task 4: Clipboard Module

**Files:**
- Create: `src/ohmyvoice/clipboard.py`
- Create: `tests/test_clipboard.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_clipboard.py
import subprocess

from ohmyvoice.clipboard import copy_to_clipboard, get_clipboard_text


def test_copy_and_read_back():
    text = "OhMyVoice test 你好 React TypeScript"
    copy_to_clipboard(text)
    result = get_clipboard_text()
    assert result == text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_clipboard.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement clipboard module**

```python
# src/ohmyvoice/clipboard.py
from AppKit import NSPasteboard, NSPasteboardTypeString


def copy_to_clipboard(text: str) -> None:
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def get_clipboard_text() -> str | None:
    pb = NSPasteboard.generalPasteboard()
    return pb.stringForType_(NSPasteboardTypeString)
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_clipboard.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/clipboard.py tests/test_clipboard.py
git commit -m "feat: clipboard module using NSPasteboard"
```

---

## Task 5: Audio Feedback Module

**Files:**
- Create: `src/ohmyvoice/audio_feedback.py`
- Create: `resources/sounds/.gitkeep`

- [ ] **Step 1: Implement audio feedback module**

Note: Audio playback is hard to unit test. We test the file-missing edge case and use manual verification for actual sound.

```python
# src/ohmyvoice/audio_feedback.py
from pathlib import Path

from AppKit import NSSound

_RESOURCES = Path(__file__).parent.parent.parent / "resources" / "sounds"

# System sounds as fallback
_SYSTEM_SOUNDS = Path("/System/Library/Sounds")


def play_start():
    _play("start.aiff", fallback="Tink.aiff")


def play_done():
    _play("done.aiff", fallback="Pop.aiff")


def _play(name: str, fallback: str = ""):
    path = _RESOURCES / name
    if not path.exists():
        path = _SYSTEM_SOUNDS / fallback
    if path.exists():
        sound = NSSound.alloc().initWithContentsOfFile_byReference_(str(path), True)
        if sound:
            sound.play()
```

- [ ] **Step 2: Create sound placeholder**

```bash
touch resources/sounds/.gitkeep
```

- [ ] **Step 3: Manual verification**

Run: `python -c "from ohmyvoice.audio_feedback import play_start, play_done; play_start(); import time; time.sleep(1); play_done()"`
Expected: Hear two system sounds (Tink and Pop). If no sound, check macOS sound settings.

- [ ] **Step 4: Commit**

```bash
git add src/ohmyvoice/audio_feedback.py resources/sounds/.gitkeep
git commit -m "feat: audio feedback with system sound fallback"
```

---

## Task 6: Notification Module

**Files:**
- Create: `src/ohmyvoice/notification.py`

- [ ] **Step 1: Implement notification module**

```python
# src/ohmyvoice/notification.py
import objc
from Foundation import NSObject


def send_notification(text: str, title: str = "OhMyVoice") -> None:
    """Send macOS notification with transcription preview."""
    preview = text[:80] + ("…" if len(text) > 80 else "")
    try:
        # Use rumps notification (simpler, works without entitlements)
        import rumps
        rumps.notification(
            title=title,
            subtitle="转写完成",
            message=preview,
        )
    except Exception:
        pass
```

Note: `rumps.notification()` wraps NSUserNotification (deprecated but works without app signing). UNUserNotificationCenter requires entitlements. For V1, rumps notifications are sufficient.

- [ ] **Step 2: Manual verification**

Run: `python -c "from ohmyvoice.notification import send_notification; send_notification('React Server Component 测试通知')"`
Expected: macOS notification appears with title "OhMyVoice" and preview text.

- [ ] **Step 3: Commit**

```bash
git add src/ohmyvoice/notification.py
git commit -m "feat: notification module using rumps notification"
```

---

## Task 7: Recorder Module

**Files:**
- Create: `src/ohmyvoice/recorder.py`
- Create: `tests/test_recorder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_recorder.py
import numpy as np

from ohmyvoice.recorder import Recorder


def test_recorder_returns_numpy_array():
    """Integration test: records 1 second of audio from default mic."""
    rec = Recorder(sample_rate=16000)
    rec.start()
    import time
    time.sleep(1)
    audio = rec.stop()

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert len(audio) > 0
    assert audio.ndim == 1  # mono


def test_recorder_duration():
    rec = Recorder(sample_rate=16000)
    rec.start()
    import time
    time.sleep(0.5)
    audio = rec.stop()
    duration = len(audio) / 16000
    assert 0.3 < duration < 1.0  # allow some tolerance


def test_list_devices():
    devices = Recorder.list_input_devices()
    assert isinstance(devices, list)
    # Should have at least the built-in mic
    assert len(devices) > 0
    assert "name" in devices[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_recorder.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement recorder**

```python
# src/ohmyvoice/recorder.py
import threading

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, sample_rate: int = 16000, device: str | int | None = None):
        self._sample_rate = sample_rate
        self._device = device
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks)
        return audio.flatten()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None and self._stream.active

    @property
    def duration(self) -> float:
        with self._lock:
            total = sum(len(c) for c in self._chunks)
        return total / self._sample_rate

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self._chunks.append(indata.copy())

    @staticmethod
    def list_input_devices() -> list[dict]:
        devices = sd.query_devices()
        result = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                result.append({
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "sample_rate": d["default_samplerate"],
                })
        return result
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_recorder.py -v`
Expected: 3 passed (requires microphone access — macOS may prompt for permission on first run)

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/recorder.py tests/test_recorder.py
git commit -m "feat: audio recorder using sounddevice with device selection"
```

---

## Task 8: ASR Module

**Files:**
- Create: `src/ohmyvoice/asr.py`
- Create: `tests/test_asr.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_asr.py
import numpy as np
import pytest

from ohmyvoice.asr import ASREngine


@pytest.fixture(scope="module")
def engine():
    """Load model once for all tests in this module. Slow (~10s first time)."""
    e = ASREngine(model_id="Qwen/Qwen3-ASR-0.6B")
    e.load()
    return e


def test_engine_loads(engine):
    assert engine.is_loaded


def test_transcribe_silence(engine):
    """Silence or near-silence should return empty or very short text."""
    silence = np.zeros(16000 * 2, dtype=np.float32)  # 2 seconds
    result = engine.transcribe(silence)
    assert isinstance(result.text, str)


def test_transcribe_returns_result_type(engine):
    # Generate a simple tone (won't produce meaningful text, but tests the pipeline)
    t = np.linspace(0, 1, 16000, dtype=np.float32)
    tone = (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32)
    result = engine.transcribe(tone)
    assert hasattr(result, "text")
    assert hasattr(result, "language")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_asr.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement ASR engine**

```python
# src/ohmyvoice/asr.py
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
        # The spec says `--prompt` which is the CLI flag name; Python API equivalent is `context`.
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_asr.py -v --timeout=120`
Expected: 3 passed (first run downloads model ~1.2GB, takes time)

Note: If model download is too slow, tests can be marked `@pytest.mark.slow` and skipped in CI.

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/asr.py tests/test_asr.py
git commit -m "feat: ASR engine wrapping mlx-qwen3-asr Session API"
```

---

## Task 9: Model Manager Module

**Files:**
- Create: `src/ohmyvoice/model_manager.py`
- Create: `tests/test_model_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_model_manager.py
from pathlib import Path

from ohmyvoice.model_manager import ModelManager


def test_model_info():
    mm = ModelManager()
    info = mm.get_model_info()
    assert "name" in info
    assert "quantization" in info


def test_model_cache_dir():
    mm = ModelManager()
    cache_dir = mm.cache_dir
    assert isinstance(cache_dir, Path)


def test_is_downloaded_false_for_nonexistent():
    mm = ModelManager(cache_dir=Path("/tmp/nonexistent_model_cache_test"))
    assert mm.is_downloaded("fake-model-9999") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_model_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement model manager**

```python
# src/ohmyvoice/model_manager.py
from pathlib import Path

from huggingface_hub import scan_cache_dir, snapshot_download


class ModelManager:
    # Known model IDs and their properties
    MODELS = {
        "Qwen3-ASR-0.6B": {
            "hf_id": "Qwen/Qwen3-ASR-0.6B",
            "size_estimate": "1.2 GB",
            "quantizations": ["fp16"],
        },
    }

    def __init__(self, cache_dir: Path | None = None):
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        self._cache_dir = cache_dir

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def get_model_info(self) -> dict:
        return {
            "name": "Qwen3-ASR-0.6B",
            "hf_id": "Qwen/Qwen3-ASR-0.6B",
            "quantization": "fp16",
            "size_estimate": "1.2 GB",
        }

    def is_downloaded(self, model_id: str = "Qwen/Qwen3-ASR-0.6B") -> bool:
        try:
            cache_info = scan_cache_dir(self._cache_dir)
            for repo in cache_info.repos:
                if repo.repo_id == model_id:
                    return True
        except Exception:
            pass
        return False

    def download(
        self,
        model_id: str = "Qwen/Qwen3-ASR-0.6B",
        progress_callback=None,
    ) -> Path:
        path = snapshot_download(
            model_id,
            cache_dir=self._cache_dir,
        )
        return Path(path)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_model_manager.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/model_manager.py tests/test_model_manager.py
git commit -m "feat: model manager with HuggingFace Hub integration"
```

---

## Task 10: Hotkey Module

**Files:**
- Create: `src/ohmyvoice/hotkey.py`

- [ ] **Step 1: Implement hotkey module**

Note: CGEventTap requires Accessibility permission and can only be tested interactively.

```python
# src/ohmyvoice/hotkey.py
import threading
from typing import Callable

import Quartz


# Modifier key mappings
_MODIFIER_FLAGS = {
    "command": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "control": Quartz.kCGEventFlagMaskControl,
}

# Common key code mappings (macOS virtual key codes)
_KEY_CODES = {
    "space": 49, "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3,
    "g": 5, "h": 4, "i": 34, "j": 38, "k": 40, "l": 37, "m": 46,
    "n": 45, "o": 31, "p": 35, "q": 12, "r": 15, "s": 1, "t": 17,
    "u": 32, "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
    "return": 36, "tab": 48, "escape": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
}


class HotkeyManager:
    def __init__(
        self,
        modifiers: list[str],
        key: str,
        on_press: Callable,
        on_release: Callable,
    ):
        self._modifiers = modifiers
        self._key = key
        self._on_press = on_press
        self._on_release = on_release
        self._tap = None
        self._thread = None
        self._running = False
        self._key_held = False

    def start(self) -> bool:
        """Start listening. Returns False if accessibility permission denied."""
        mask = (
            1 << Quartz.kCGEventKeyDown
            | 1 << Quartz.kCGEventKeyUp
            | 1 << Quartz.kCGEventFlagsChanged
        )

        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )

        if self._tap is None:
            return False  # accessibility permission not granted

        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._running = True

        def _run():
            loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(loop, source, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(self._tap, True)
            while self._running:
                Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.5, False)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, False)
        if self._thread:
            self._thread.join(timeout=2)

    def update_hotkey(self, modifiers: list[str], key: str):
        self._modifiers = modifiers
        self._key = key
        self._key_held = False

    def _callback(self, proxy, event_type, event, refcon):
        key_code = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventKeycode
        )
        flags = Quartz.CGEventGetFlags(event)

        target_code = _KEY_CODES.get(self._key)
        if target_code is None:
            return event

        # Check modifiers match
        required_flags = 0
        for mod in self._modifiers:
            required_flags |= _MODIFIER_FLAGS.get(mod, 0)

        modifiers_match = (flags & required_flags) == required_flags

        if event_type == Quartz.kCGEventKeyDown and not self._key_held:
            if key_code == target_code and modifiers_match:
                self._key_held = True
                self._on_press()

        elif event_type == Quartz.kCGEventKeyUp:
            if key_code == target_code and self._key_held:
                self._key_held = False
                self._on_release()

        return event
```

- [ ] **Step 2: Manual verification**

```python
# Run interactively:
# python -c "
# from ohmyvoice.hotkey import HotkeyManager
# hk = HotkeyManager(['option'], 'space', lambda: print('PRESS'), lambda: print('RELEASE'))
# ok = hk.start()
# print('Started:', ok)
# if not ok: print('Grant Accessibility permission in System Settings > Privacy & Security')
# import time; time.sleep(30)
# hk.stop()
# "
```

Expected: Press ⌥Space → prints "PRESS". Release → prints "RELEASE". If returns `False`, need Accessibility permission.

- [ ] **Step 3: Commit**

```bash
git add src/ohmyvoice/hotkey.py
git commit -m "feat: global hotkey using CGEventTap with push-to-talk support"
```

---

## Task 11: Autostart Module

**Files:**
- Create: `src/ohmyvoice/autostart.py`
- Create: `tests/test_autostart.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_autostart.py
import sys
from pathlib import Path

from ohmyvoice.autostart import get_plist_path, generate_plist


def test_plist_path():
    path = get_plist_path()
    assert "LaunchAgents" in str(path)
    assert "ohmyvoice" in str(path).lower()


def test_generate_plist():
    xml = generate_plist(python_path="/usr/bin/python3", module="ohmyvoice.app")
    assert "com.ohmyvoice.app" in xml
    assert "/usr/bin/python3" in xml
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_autostart.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement autostart**

```python
# src/ohmyvoice/autostart.py
import sys
from pathlib import Path

_LABEL = "com.ohmyvoice.app"


def get_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def generate_plist(
    python_path: str | None = None,
    module: str = "ohmyvoice.app",
) -> str:
    if python_path is None:
        python_path = sys.executable
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>{module}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""


def enable():
    path = get_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_plist())


def disable():
    path = get_plist_path()
    if path.exists():
        path.unlink()


def is_enabled() -> bool:
    return get_plist_path().exists()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_autostart.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/autostart.py tests/test_autostart.py
git commit -m "feat: autostart via launchd plist"
```

---

## Task 12: Menu Bar App (Core Integration)

**Files:**
- Create: `src/ohmyvoice/app.py`
- Create: placeholder icons in `resources/icons/`

This is the main integration task. It wires all modules together.

- [ ] **Step 1: Create placeholder menu bar icons**

Generate 22x22 PNG icons. For now, use simple colored circles as placeholders:

```python
# Run once to generate placeholder icons:
# python -c "
# from PIL import Image, ImageDraw
# import os
# os.makedirs('resources/icons', exist_ok=True)
# for name, color in [('mic_idle', (128,128,128)), ('mic_recording', (239,68,68)),
#                      ('mic_processing', (167,139,250)), ('mic_done', (52,211,153))]:
#     img = Image.new('RGBA', (22, 22), (0, 0, 0, 0))
#     draw = ImageDraw.Draw(img)
#     draw.ellipse([3, 3, 19, 19], fill=(*color, 255))
#     img.save(f'resources/icons/{name}.png')
# "
```

If Pillow not available, create icons manually or use any 22x22 PNGs.

- [ ] **Step 2: Implement app.py**

```python
# src/ohmyvoice/app.py
import threading
import time
from pathlib import Path

import rumps

from ohmyvoice.asr import ASREngine
from ohmyvoice.audio_feedback import play_done, play_start
from ohmyvoice.clipboard import copy_to_clipboard
from ohmyvoice.history import HistoryDB
from ohmyvoice.hotkey import HotkeyManager
from ohmyvoice.notification import send_notification
from ohmyvoice.recorder import Recorder
from ohmyvoice.settings import Settings

_ICONS = Path(__file__).parent.parent.parent / "resources" / "icons"


class OhMyVoiceApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="OhMyVoice",
            icon=str(_ICONS / "mic_idle.png"),
            quit_button=None,
        )
        self.template = True  # auto dark/light mode for idle icon

        self._settings = Settings()
        self._history = HistoryDB()
        self._recorder = Recorder(
            sample_rate=16000,
            device=self._settings.input_device,
        )
        self._engine = ASREngine()
        self._hotkey: HotkeyManager | None = None
        self._state = "idle"  # idle | recording | processing | done

        self._build_menu()
        self._load_model_async()

    def _build_menu(self):
        self.menu = [
            rumps.MenuItem("状态: 加载中...", callback=None),
            None,  # separator
            rumps.MenuItem("最近转写", callback=None),
            None,
            rumps.MenuItem("设置...", callback=self._on_settings),
            rumps.MenuItem("全部历史", callback=self._on_history),
            None,
            rumps.MenuItem("退出", callback=self._on_quit),
        ]

    def _load_model_async(self):
        def _load():
            try:
                self._engine.load()
                self._set_state("idle")
                self.menu["状态: 加载中..."].title = (
                    f"就绪 · {self._settings.hotkey_display}"
                )
                self._start_hotkey()
            except Exception as e:
                self.menu["状态: 加载中..."].title = f"模型加载失败: {e}"

        threading.Thread(target=_load, daemon=True).start()

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
        if self._state != "idle" or not self._engine.is_loaded:
            return
        self._set_state("recording")
        if self._settings.sound_feedback:
            play_start()
        self._recorder.start()
        # Enforce max recording duration
        max_sec = self._settings.max_recording_seconds
        self._max_rec_timer = rumps.Timer(
            lambda t: (t.stop(), self._on_hotkey_release()),
            max_sec,
        )
        self._max_rec_timer.start()

    def _on_hotkey_release(self):
        if self._state != "recording":
            return
        if hasattr(self, "_max_rec_timer"):
            self._max_rec_timer.stop()
        audio = self._recorder.stop()
        if len(audio) < 1600:  # < 0.1s, ignore accidental taps
            self._set_state("idle")
            return
        self._set_state("processing")
        threading.Thread(
            target=self._process_audio, args=(audio,), daemon=True
        ).start()

    def _process_audio(self, audio):
        try:
            context = self._settings.get_active_prompt()
            result = self._engine.transcribe(audio, context=context)
            text = result.text
            if text:
                copy_to_clipboard(text)
                self._history.add(text, duration=result.duration_seconds)
                self._history.prune(self._settings.history_max_entries)
                self._update_recent_menu()
                if self._settings.sound_feedback:
                    play_done()
                if self._settings.notification_on_complete:
                    send_notification(text)
            self._set_state("done")
            time.sleep(1)
            self._set_state("idle")
        except Exception as e:
            print(f"ASR error: {e}")
            self._set_state("idle")

    def _set_state(self, state: str):
        self._state = state
        icon_map = {
            "idle": ("mic_idle.png", True),
            "recording": ("mic_recording.png", False),
            "processing": ("mic_processing.png", False),
            "done": ("mic_done.png", False),
        }
        icon_name, template = icon_map.get(state, ("mic_idle.png", True))
        self.icon = str(_ICONS / icon_name)
        self.template = template

    def _update_recent_menu(self):
        records = self._history.recent(3)
        sub = self.menu["最近转写"]
        sub.clear()
        for r in records:
            preview = r["text"][:40] + ("…" if len(r["text"]) > 40 else "")
            item = rumps.MenuItem(
                preview,
                callback=lambda _, text=r["text"]: copy_to_clipboard(text),
            )
            sub[preview] = item

    def _on_settings(self, _):
        # V1: simple dialog for hotkey. Full settings window is a follow-up.
        w = rumps.Window(
            message="输入新的快捷键（如 option+space）:",
            title="OhMyVoice 设置",
            default_text=f"{'+'.join(self._settings.hotkey_modifiers)}+{self._settings.hotkey_key}",
            ok="保存",
            cancel="取消",
            dimensions=(300, 24),
        )
        resp = w.run()
        if resp.clicked:
            parts = resp.text.strip().lower().split("+")
            if len(parts) >= 2:
                self._settings.hotkey_modifiers = parts[:-1]
                self._settings.hotkey_key = parts[-1]
                self._settings.save()
                if self._hotkey:
                    self._hotkey.update_hotkey(
                        self._settings.hotkey_modifiers,
                        self._settings.hotkey_key,
                    )

    def _on_history(self, _):
        records = self._history.recent(20)
        if not records:
            rumps.alert("历史记录", "暂无转写记录")
            return
        text = "\n\n".join(
            f"[{r['created_at']}] {r['text']}" for r in records
        )
        w = rumps.Window(
            message=text,
            title="转写历史",
            ok="关闭",
            cancel=None,
            dimensions=(500, 300),
        )
        w.run()

    def _on_quit(self, _):
        if self._hotkey:
            self._hotkey.stop()
        self._history.close()
        rumps.quit_application()


def main():
    OhMyVoiceApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Manual smoke test**

```bash
python -m ohmyvoice.app
```

Expected:
1. Menu bar icon appears (gray circle)
2. After model loads (~5-10s first time), status shows "就绪"
3. ⌥Space held → icon turns red (recording)
4. Release → icon turns purple (processing) → green (done) → gray (idle)
5. Text appears in clipboard

- [ ] **Step 4: Commit**

```bash
git add src/ohmyvoice/app.py resources/icons/
git commit -m "feat: menu bar app integrating all modules"
```

---

## Task 13: End-to-End Verification & Polish

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All unit tests pass. Note which tests require hardware (mic, accessibility).

- [ ] **Step 2: Test the complete workflow**

1. Start: `python -m ohmyvoice.app`
2. Wait for model load
3. Hold ⌥Space, say "帮我用 React Server Component 重构这个 API endpoint"
4. Release
5. ⌘V in any text field → verify transcription quality
6. Click menu bar icon → verify history shows the transcription
7. Click a history item → verify it copies to clipboard

- [ ] **Step 3: Test settings persistence**

1. Open Settings → change hotkey to ⌃R
2. Quit app, restart
3. Verify new hotkey works

- [ ] **Step 4: Test error cases**

1. Disconnect external mic (if using one) → verify fallback to built-in
2. Try recording with model still loading → verify no crash

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: OhMyVoice v0.1.0 — local speech-to-text menu bar app"
```
