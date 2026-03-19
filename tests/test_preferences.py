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
