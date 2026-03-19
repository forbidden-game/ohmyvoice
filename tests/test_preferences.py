import pytest
from AppKit import NSApplication
from ohmyvoice.settings import Settings


@pytest.fixture(autouse=True)
def _ensure_nsapp():
    """NSApplication must exist before creating any NSWindow."""
    NSApplication.sharedApplication()


@pytest.fixture
def mock_app(tmp_path):
    class _MockEngine:
        is_loaded = True

    class _MockApp:
        def __init__(self):
            self._settings = Settings(config_dir=tmp_path)
            self._engine = _MockEngine()
            self._hotkey = None
            self._recorder = None

    return _MockApp()


def test_window_creates_with_correct_title(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._window is not None
    assert pw._window.title() == "OhMyVoice 设置"


def test_toolbar_has_four_items(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    toolbar = pw._window.toolbar()
    assert toolbar is not None
    assert len(toolbar.items()) == 4


def test_default_tab_is_general(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._current_tab == "general"


def test_tab_switching(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    for tab in ["audio", "recognition", "about", "general"]:
        pw._switch_tab(tab)
        assert pw._current_tab == tab


def test_general_tab_has_hotkey_display(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._hotkey_label is not None
    # hotkey_display returns "⌥SPACE" (uppercase)
    assert "SPACE" in pw._hotkey_label.stringValue()


def test_general_tab_language_popup(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._language_popup is not None
    # Default is "auto" → index 0 ("自动检测")
    assert pw._language_popup.indexOfSelectedItem() == 0


def test_general_tab_autostart_switch(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._autostart_switch is not None
    # Default is False → state 0
    assert pw._autostart_switch.state() == 0


def test_audio_tab_has_mic_popup(mock_app):
    from ohmyvoice.preferences import PreferencesWindow
    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._mic_popup is not None
    # First item should be "系统默认"
    assert pw._mic_popup.itemTitleAtIndex_(0) == "系统默认"


def test_audio_tab_sound_feedback_switch(mock_app):
    from ohmyvoice.preferences import PreferencesWindow
    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._sound_switch is not None
    # Default is True → state 1
    assert pw._sound_switch.state() == 1


def test_recognition_tab_template_popup(mock_app):
    from ohmyvoice.preferences import PreferencesWindow
    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._template_popup is not None
    # Default template is "coding" → index 0
    assert pw._template_popup.indexOfSelectedItem() == 0


def test_recognition_tab_prompt_readonly_for_presets(mock_app):
    from ohmyvoice.preferences import PreferencesWindow
    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._prompt_textview is not None
    # Preset templates should be non-editable
    assert pw._prompt_textview.isEditable() is False


def test_recognition_tab_quantization_popup(mock_app):
    from ohmyvoice.preferences import PreferencesWindow
    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._quant_popup is not None
    # Default is "4bit" → index 0 ("4-bit")
    assert pw._quant_popup.indexOfSelectedItem() == 0


def test_about_tab_shows_app_name(mock_app):
    from ohmyvoice.preferences import PreferencesWindow
    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._app_name_label is not None
    assert pw._app_name_label.stringValue() == "OhMyVoice"


def test_hotkey_manager_pause_resume():
    """pause/resume methods exist and don't crash when no tap is active."""
    from ohmyvoice.hotkey import HotkeyManager
    hm = HotkeyManager(
        modifiers=["option"], key="space",
        on_press=lambda: None, on_release=lambda: None,
    )
    hm.pause()
    hm.resume()


def test_hotkey_capture_starts(mock_app):
    from ohmyvoice.preferences import PreferencesWindow
    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._record_btn is not None
    pw._start_hotkey_capture()
    assert pw._record_btn.title() == "按下新组合..."
    pw._cancel_hotkey_capture()
    assert pw._record_btn.title() == "录制"
