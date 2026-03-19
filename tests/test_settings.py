import json
from pathlib import Path
from ohmyvoice.settings import Settings, _PROMPT_VERSION

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
    assert s2.sound_feedback is True

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
    assert s.hotkey_key == "space"

def test_old_prompt_version_resets_templates(tmp_path):
    # Simulate a settings file saved at an old prompt version with a stale template.
    old_settings = {
        "hotkey": {"modifiers": ["option"], "key": "space"},
        "prompt": {
            "active_template": "coding",
            "custom_prompt": "",
            "templates": {
                "coding": "stale old template without new brands",
                "meeting": "old meeting template",
                "general": "",
            },
        },
        "language": "zh",
        "prompt_version": 0,
    }
    (tmp_path / "settings.json").write_text(json.dumps(old_settings))
    s = Settings(config_dir=tmp_path)
    # Templates must be reset to current defaults.
    assert "stale old template" not in s.prompt_templates["coding"]
    assert s._data["prompt_version"] == _PROMPT_VERSION
    # Unrelated user setting must survive.
    assert s.language == "zh"
    # The updated version must be persisted.
    reloaded = json.loads((tmp_path / "settings.json").read_text())
    assert reloaded["prompt_version"] == _PROMPT_VERSION
