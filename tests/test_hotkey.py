from unittest.mock import MagicMock

import ohmyvoice.hotkey as hotkey
from ohmyvoice.hotkey import HotkeyManager


def _mock_keyboard_event(monkeypatch, key_code: int, flags: int):
    monkeypatch.setattr(
        hotkey.Quartz,
        "CGEventGetIntegerValueField",
        lambda event, field: key_code,
    )
    monkeypatch.setattr(
        hotkey.Quartz,
        "CGEventGetFlags",
        lambda event: flags,
    )


def test_matching_hotkey_events_are_suppressed(monkeypatch):
    on_press = MagicMock()
    on_release = MagicMock()
    manager = HotkeyManager(["option"], "space", on_press, on_release)
    event = object()
    _mock_keyboard_event(
        monkeypatch,
        key_code=49,
        flags=hotkey.Quartz.kCGEventFlagMaskAlternate,
    )

    assert manager._callback(None, hotkey.Quartz.kCGEventKeyDown, event, None) is None
    assert manager._callback(None, hotkey.Quartz.kCGEventKeyDown, event, None) is None
    assert manager._callback(None, hotkey.Quartz.kCGEventKeyUp, event, None) is None

    on_press.assert_called_once()
    on_release.assert_called_once()


def test_non_matching_events_pass_through(monkeypatch):
    on_press = MagicMock()
    on_release = MagicMock()
    manager = HotkeyManager(["option"], "space", on_press, on_release)
    event = object()
    _mock_keyboard_event(
        monkeypatch,
        key_code=0,
        flags=hotkey.Quartz.kCGEventFlagMaskAlternate,
    )

    assert manager._callback(None, hotkey.Quartz.kCGEventKeyDown, event, None) is event

    on_press.assert_not_called()
    on_release.assert_not_called()


def test_tap_is_reenabled_after_timeout(monkeypatch):
    manager = HotkeyManager(["option"], "space", MagicMock(), MagicMock())
    manager._tap = object()
    enable = MagicMock()
    monkeypatch.setattr(hotkey.Quartz, "CGEventTapEnable", enable)

    event = object()
    assert (
        manager._callback(None, hotkey.Quartz.kCGEventTapDisabledByTimeout, event, None)
        is event
    )

    enable.assert_called_once_with(manager._tap, True)
