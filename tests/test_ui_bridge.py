import json
from unittest.mock import MagicMock, patch
from ohmyvoice.ui_bridge import UIBridge


def test_build_state_message():
    app = MagicMock()
    app._settings.model_name = "Qwen3-ASR-0.6B"
    app._settings.model_quantization = "4bit"
    app._manager.worker_state = "ready"

    bridge = UIBridge(app)
    msg = bridge._build_state_message()

    assert msg["type"] == "state"
    assert msg["model_loaded"] is True
    assert msg["model_name"] == "Qwen3-ASR-0.6B"
    assert msg["quantization"] == "4bit"
    assert isinstance(msg["mic_devices"], list)
    assert "disk_usage" in msg


def test_handle_reload_model():
    app = MagicMock()
    app._settings.model_quantization = "4bit"
    bridge = UIBridge(app)
    bridge._process = MagicMock()
    bridge._process.stdin = MagicMock()
    bridge._process.poll.return_value = None  # process still running

    bridge._handle_message({"type": "reload_model", "quantization": "8bit"})
    # Verify quantization updated in memory immediately
    assert app._settings.model_quantization == "8bit"
    # Verify manager.reload_model called
    app._manager.reload_model.assert_called_once_with("8bit")


def test_handle_toggle_autostart():
    app = MagicMock()
    bridge = UIBridge(app)
    bridge._process = MagicMock()
    bridge._process.stdin = MagicMock()

    bridge._handle_message({"type": "toggle_autostart", "enabled": True})
    # autostart module should be called


def test_handle_start_hotkey_capture():
    app = MagicMock()
    bridge = UIBridge(app)
    bridge._process = MagicMock()
    bridge._process.stdin = MagicMock()

    bridge._handle_message({"type": "start_hotkey_capture"})
    app._hotkey.pause.assert_called_once()


def test_handle_finish_hotkey_capture():
    app = MagicMock()
    bridge = UIBridge(app)
    bridge._process = MagicMock()
    bridge._process.stdin = MagicMock()

    bridge._handle_message({
        "type": "finish_hotkey_capture",
        "modifiers": ["command"],
        "key": "space",
    })
    app._hotkey.update_hotkey.assert_called_once_with(["command"], "space")
    app._hotkey.resume.assert_called_once()


def test_handle_clear_history():
    app = MagicMock()
    bridge = UIBridge(app)
    bridge._process = MagicMock()
    bridge._process.stdin = MagicMock()

    bridge._handle_message({"type": "clear_history"})
    app._history.clear.assert_called_once()


def test_handle_close():
    app = MagicMock()
    bridge = UIBridge(app)
    bridge._process = MagicMock()
    bridge._process.stdin = MagicMock()
    bridge._schedule_menu_update = MagicMock()

    bridge._handle_message({"type": "close"})
    app._settings.reload.assert_called_once()


def test_find_binary_frozen_before_dev(tmp_path, monkeypatch):
    """In frozen mode, check bundle path before dev path."""
    import sys
    import ohmyvoice.ui_bridge as ub

    # Create a "dev" binary at a path that _find_binary's dev-path lookup will find
    fake_project = tmp_path / "project"
    fake_src = fake_project / "src" / "ohmyvoice"
    fake_src.mkdir(parents=True)
    dev_binary = fake_project / "ui" / ".build" / "release" / "ohmyvoice-ui"
    dev_binary.parent.mkdir(parents=True)
    dev_binary.touch()

    # Also create a "frozen" binary
    frozen_binary = tmp_path / "bundle" / "Contents" / "MacOS" / "ohmyvoice-ui"
    frozen_binary.parent.mkdir(parents=True)
    frozen_binary.touch()
    fake_exe = str(frozen_binary.parent / "ohmyvoice")

    app = MagicMock()
    bridge = UIBridge(app)

    # Monkeypatch __file__ so dev path resolves to our tmp tree
    monkeypatch.setattr(ub, "__file__", str(fake_src / "ui_bridge.py"))

    with monkeypatch.context() as m:
        m.setattr(sys, "frozen", True, raising=False)
        m.setattr(sys, "executable", fake_exe)
        result = bridge._find_binary()

    # Must find the frozen binary, not the dev one
    assert result == frozen_binary
