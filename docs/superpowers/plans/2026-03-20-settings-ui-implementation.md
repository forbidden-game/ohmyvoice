# Settings UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `rumps.Window` text dialog with a full NSWindow preferences window (4 toolbar tabs).

**Architecture:** Single new module `preferences.py` containing `PreferencesWindow` class. Uses PyObjC AppKit for NSWindow + NSToolbar + standard controls. Each tab is a flipped NSView with grouped form rows. Settings changes are saved immediately (no Apply/Cancel). Minor modifications to `app.py` (wire up) and `hotkey.py` (add pause/resume).

**Tech Stack:** PyObjC (AppKit, Foundation), existing Settings/Recorder/ASREngine/HotkeyManager

**Spec:** `docs/superpowers/specs/2026-03-20-settings-ui-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ohmyvoice/preferences.py` | Create | PreferencesWindow, toolbar delegate, form helpers, all 4 tab builders, hotkey capture |
| `tests/test_preferences.py` | Create | Tests for window structure, tab content, settings binding, hotkey capture |
| `src/ohmyvoice/hotkey.py` | Modify | Add `pause()` / `resume()` methods (2 lines each) |
| `src/ohmyvoice/app.py` | Modify | Replace `_on_settings` to use PreferencesWindow; fix `_load_model_async` to respect quantization setting |

---

### Task 1: PreferencesWindow skeleton + toolbar

**Files:**
- Create: `src/ohmyvoice/preferences.py`
- Create: `tests/test_preferences.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_preferences.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preferences.py -v`
Expected: `ModuleNotFoundError: No module named 'ohmyvoice.preferences'`

- [ ] **Step 3: Write the implementation**

```python
# src/ohmyvoice/preferences.py
"""macOS native preferences window with 4 toolbar tabs."""

import objc
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSImage,
    NSToolbar,
    NSToolbarItem,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect

_WINDOW_WIDTH = 520
_TAB_IDS = ["general", "audio", "recognition", "about"]
_TAB_LABELS = {
    "general": "通用",
    "audio": "音频",
    "recognition": "识别",
    "about": "关于",
}
_TAB_ICONS = {
    "general": "gearshape",
    "audio": "waveform",
    "recognition": "sparkles",
    "about": "info.circle",
}


class _FlippedView(NSView):
    """NSView with top-left origin (y increases downward)."""

    def isFlipped(self):
        return True


class _ToolbarDelegate(NSView):
    """NSToolbar delegate that routes tab clicks to PreferencesWindow."""

    def init(self):
        self = objc.super(_ToolbarDelegate, self).init()
        if self is None:
            return None
        self._callback = None
        return self

    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
        self, toolbar, ident, flag
    ):
        item = NSToolbarItem.alloc().initWithItemIdentifier_(ident)
        item.setLabel_(_TAB_LABELS.get(ident, ident))
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            _TAB_ICONS.get(ident, "questionmark"),
            _TAB_LABELS.get(ident, ""),
        )
        if image:
            item.setImage_(image)
        item.setTarget_(self)
        item.setAction_("onItemClick:")
        return item

    def onItemClick_(self, sender):
        if self._callback:
            self._callback(sender.itemIdentifier())

    def toolbarAllowedItemIdentifiers_(self, toolbar):
        return _TAB_IDS

    def toolbarDefaultItemIdentifiers_(self, toolbar):
        return _TAB_IDS

    def toolbarSelectableItemIdentifiers_(self, toolbar):
        return _TAB_IDS


class PreferencesWindow:
    """NSWindow-based preferences with 4 toolbar tabs."""

    def __init__(self, app):
        self._app = app
        self._window = None
        self._toolbar_delegate = None
        self._views = {}
        self._current_tab = None

    def show(self):
        """Show or bring to front the preferences window."""
        if self._window is None:
            self._build()
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def _build(self):
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
        )
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, 300),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("OhMyVoice 设置")
        self._window.center()

        self._views = {
            "general": self._build_general_view(),
            "audio": self._build_audio_view(),
            "recognition": self._build_recognition_view(),
            "about": self._build_about_view(),
        }

        self._toolbar_delegate = _ToolbarDelegate.alloc().init()
        self._toolbar_delegate._callback = self._switch_tab
        toolbar = NSToolbar.alloc().initWithIdentifier_("OhMyVoicePrefs")
        toolbar.setDelegate_(self._toolbar_delegate)
        toolbar.setDisplayMode_(1)  # NSToolbarDisplayModeIconAndLabel
        toolbar.setAllowsUserCustomization_(False)
        self._window.setToolbar_(toolbar)
        toolbar.setSelectedItemIdentifier_("general")
        self._switch_tab("general")

    def _switch_tab(self, tab_id):
        if tab_id == self._current_tab:
            return
        view = self._views.get(tab_id)
        if view is None:
            return
        self._current_tab = tab_id
        self._window.setContentView_(view)
        # Resize window height keeping top-left corner fixed
        frame = self._window.frame()
        content_rect = self._window.contentRectForFrameRect_(frame)
        chrome_h = frame.size.height - content_rect.size.height
        new_h = view.frame().size.height + chrome_h
        new_frame = NSMakeRect(
            frame.origin.x,
            frame.origin.y + frame.size.height - new_h,
            frame.size.width,
            new_h,
        )
        self._window.setFrame_display_animate_(new_frame, True, True)

    # Placeholder tab builders — replaced in subsequent tasks
    def _build_general_view(self):
        return _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, 300)
        )

    def _build_audio_view(self):
        return _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, 200)
        )

    def _build_recognition_view(self):
        return _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, 280)
        )

    def _build_about_view(self):
        return _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, 260)
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preferences.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/preferences.py tests/test_preferences.py
git commit -m "feat: PreferencesWindow skeleton with NSToolbar and tab switching"
```

---

### Task 2: Form layout helpers + General tab

**Files:**
- Modify: `src/ohmyvoice/preferences.py`
- Modify: `tests/test_preferences.py`

- [ ] **Step 1: Add tests for general tab**

Append to `tests/test_preferences.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preferences.py::test_general_tab_has_hotkey_display -v`
Expected: `AttributeError: 'PreferencesWindow' object has no attribute '_hotkey_label'`

- [ ] **Step 3: Add imports, helpers, and implement `_build_general_view`**

Add these imports to the top of `preferences.py`:

```python
from AppKit import (
    # ... existing imports ...
    NSBox,
    NSButton,
    NSColor,
    NSFont,
    NSPopUpButton,
    NSSwitch,
    NSTextField,
)
```

Add constants below existing ones:

```python
_PADDING = 24
_CONTENT_W = _WINDOW_WIDTH - 2 * _PADDING
_ROW_H = 36
_ROW_H_SUB = 48
_SECTION_GAP = 16
_INNER_PAD = 14
```

Add the control reference attributes to `PreferencesWindow.__init__`:

```python
# Control references
self._hotkey_label = None
self._record_btn = None
self._language_popup = None
self._autostart_switch = None
self._notification_switch = None
self._history_limit_field = None
```

Add helper methods to `PreferencesWindow`:

```python
def _section_header(self, parent, text, y):
    """Add small uppercase section label. Returns new y."""
    label = NSTextField.labelWithString_(text)
    label.setFont_(NSFont.systemFontOfSize_weight_(11, 0.3))
    label.setTextColor_(NSColor.secondaryLabelColor())
    label.setFrame_(NSMakeRect(_PADDING, y, _CONTENT_W, 16))
    parent.addSubview_(label)
    return y + 22

def _group_box(self, parent, y, height):
    """Create a rounded background box at y with given height. Returns the box."""
    box = NSBox.alloc().initWithFrame_(
        NSMakeRect(_PADDING, y, _CONTENT_W, height)
    )
    box.setBoxType_(4)  # NSBoxCustom
    box.setBorderWidth_(0)
    box.setCornerRadius_(8)
    box.setFillColor_(NSColor.controlBackgroundColor())
    box.setContentViewMargins_((0, 0))
    parent.addSubview_(box)
    return box

def _row_in_group(self, group, label_text, control, row_y, sublabel=None):
    """Place a label + control row inside a group box. Returns new row_y."""
    h = _ROW_H_SUB if sublabel else _ROW_H
    gw = group.frame().size.width

    lbl = NSTextField.labelWithString_(label_text)
    lbl.setFont_(NSFont.systemFontOfSize_(13))
    if sublabel:
        lbl.setFrame_(NSMakeRect(_INNER_PAD, row_y + 6, 200, 17))
        sub = NSTextField.labelWithString_(sublabel)
        sub.setFont_(NSFont.systemFontOfSize_(11))
        sub.setTextColor_(NSColor.secondaryLabelColor())
        sub.setFrame_(NSMakeRect(_INNER_PAD, row_y + 24, 300, 14))
        group.addSubview_(sub)
    else:
        lbl.setFrame_(NSMakeRect(_INNER_PAD, row_y + (h - 17) // 2, 200, 17))
    group.addSubview_(lbl)

    cw = control.frame().size.width
    ch = control.frame().size.height
    control.setFrame_(NSMakeRect(
        gw - _INNER_PAD - cw, row_y + (h - ch) // 2, cw, ch
    ))
    group.addSubview_(control)
    return row_y + h

def _separator_in_group(self, group, y):
    """Add a 1px separator line inside a group box."""
    gw = group.frame().size.width
    sep = NSBox.alloc().initWithFrame_(
        NSMakeRect(_INNER_PAD, y, gw - 2 * _INNER_PAD, 1)
    )
    sep.setBoxType_(2)  # NSBoxSeparator
    group.addSubview_(sep)
```

Replace `_build_general_view` placeholder:

```python
def _build_general_view(self):
    s = self._app._settings
    view = _FlippedView.alloc().initWithFrame_(
        NSMakeRect(0, 0, _WINDOW_WIDTH, 0)  # height set at end
    )
    y = 20

    # --- Hotkey section ---
    y = self._section_header(view, "快捷键", y)
    box = self._group_box(view, y, _ROW_H_SUB)
    ry = 0

    # Hotkey display + record button
    self._hotkey_label = NSTextField.labelWithString_(s.hotkey_display)
    self._hotkey_label.setFont_(NSFont.monospacedSystemFontOfSize_weight_(14, 0.5))
    self._hotkey_label.setAlignment_(1)  # NSTextAlignmentCenter
    self._hotkey_label.setFrame_(NSMakeRect(0, 0, 100, 22))

    self._record_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 56, 24))
    self._record_btn.setTitle_("录制")
    self._record_btn.setBezelStyle_(1)  # NSBezelStyleRounded
    self._record_btn.setTarget_(self._action_delegate)
    self._record_btn.setAction_("onRecordHotkey:")

    # Combine hotkey label and button in a container
    combo = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 170, 24))
    self._hotkey_label.setFrame_(NSMakeRect(0, 1, 100, 22))
    self._record_btn.setFrame_(NSMakeRect(108, 0, 62, 24))
    combo.addSubview_(self._hotkey_label)
    combo.addSubview_(self._record_btn)

    lbl = NSTextField.labelWithString_("按住说话")
    lbl.setFont_(NSFont.systemFontOfSize_(13))
    lbl.setFrame_(NSMakeRect(_INNER_PAD, 6, 200, 17))
    box.addSubview_(lbl)
    sub = NSTextField.labelWithString_("按住录音，松开转写")
    sub.setFont_(NSFont.systemFontOfSize_(11))
    sub.setTextColor_(NSColor.secondaryLabelColor())
    sub.setFrame_(NSMakeRect(_INNER_PAD, 24, 200, 14))
    box.addSubview_(sub)
    cw = combo.frame().size.width
    combo.setFrame_(NSMakeRect(
        _CONTENT_W - _INNER_PAD - cw, (_ROW_H_SUB - 24) // 2, cw, 24
    ))
    box.addSubview_(combo)

    y += _ROW_H_SUB + _SECTION_GAP

    # --- Behavior section ---
    y = self._section_header(view, "行为", y)
    behavior_h = _ROW_H * 3
    box = self._group_box(view, y, behavior_h)
    ry = 0

    # Language popup
    _LANG_OPTIONS = ["自动检测", "中文为主", "英文为主"]
    _LANG_VALUES = ["auto", "zh", "en"]
    self._language_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(0, 0, 120, 25), False
    )
    self._language_popup.addItemsWithTitles_(_LANG_OPTIONS)
    idx = _LANG_VALUES.index(s.language) if s.language in _LANG_VALUES else 0
    self._language_popup.selectItemAtIndex_(idx)
    self._language_popup.setTarget_(self._action_delegate)
    self._language_popup.setAction_("onLanguageChanged:")
    ry = self._row_in_group(box, "语言偏好", self._language_popup, ry)
    self._separator_in_group(box, ry)

    # Autostart switch
    self._autostart_switch = NSSwitch.alloc().initWithFrame_(
        NSMakeRect(0, 0, 38, 22)
    )
    self._autostart_switch.setState_(1 if s.autostart else 0)
    self._autostart_switch.setTarget_(self._action_delegate)
    self._autostart_switch.setAction_("onAutostartChanged:")
    ry = self._row_in_group(box, "开机自启", self._autostart_switch, ry)
    self._separator_in_group(box, ry)

    # Notification switch
    self._notification_switch = NSSwitch.alloc().initWithFrame_(
        NSMakeRect(0, 0, 38, 22)
    )
    self._notification_switch.setState_(1 if s.notification_on_complete else 0)
    self._notification_switch.setTarget_(self._action_delegate)
    self._notification_switch.setAction_("onNotificationChanged:")
    ry = self._row_in_group(box, "完成通知", self._notification_switch, ry)

    y += behavior_h + _SECTION_GAP

    # --- Data section ---
    y = self._section_header(view, "数据", y)
    box = self._group_box(view, y, _ROW_H_SUB)

    self._history_limit_field = NSTextField.alloc().initWithFrame_(
        NSMakeRect(0, 0, 60, 22)
    )
    self._history_limit_field.setIntegerValue_(s.history_max_entries)
    self._history_limit_field.setAlignment_(2)  # NSTextAlignmentRight
    self._history_limit_field.setFont_(NSFont.systemFontOfSize_(12))

    unit_label = NSTextField.labelWithString_("条")
    unit_label.setFont_(NSFont.systemFontOfSize_(12))
    unit_label.setTextColor_(NSColor.secondaryLabelColor())

    combo = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 86, 22))
    self._history_limit_field.setFrame_(NSMakeRect(0, 0, 60, 22))
    unit_label.setFrame_(NSMakeRect(66, 2, 20, 17))
    combo.addSubview_(self._history_limit_field)
    combo.addSubview_(unit_label)

    lbl = NSTextField.labelWithString_("历史记录上限")
    lbl.setFont_(NSFont.systemFontOfSize_(13))
    lbl.setFrame_(NSMakeRect(_INNER_PAD, 6, 200, 17))
    box.addSubview_(lbl)
    sub = NSTextField.labelWithString_("超出后自动删除最旧记录")
    sub.setFont_(NSFont.systemFontOfSize_(11))
    sub.setTextColor_(NSColor.secondaryLabelColor())
    sub.setFrame_(NSMakeRect(_INNER_PAD, 24, 260, 14))
    box.addSubview_(sub)
    cw2 = combo.frame().size.width
    combo.setFrame_(NSMakeRect(
        _CONTENT_W - _INNER_PAD - cw2, (_ROW_H_SUB - 22) // 2, cw2, 22
    ))
    box.addSubview_(combo)

    y += _ROW_H_SUB + 20  # bottom padding
    view.setFrame_(NSMakeRect(0, 0, _WINDOW_WIDTH, y))
    return view
```

Also add `_action_delegate` attribute and class. Add to `__init__`:

```python
self._action_delegate = _ActionDelegate.alloc().init()
self._action_delegate._prefs = self
```

Add the action delegate class (below `_ToolbarDelegate`):

```python
class _ActionDelegate(NSView):
    """Handles target-action callbacks from all preference controls."""

    def init(self):
        self = objc.super(_ActionDelegate, self).init()
        if self is None:
            return None
        self._prefs = None
        return self

    def _save(self):
        self._prefs._app._settings.save()

    # --- General tab ---

    def onLanguageChanged_(self, sender):
        values = ["auto", "zh", "en"]
        idx = sender.indexOfSelectedItem()
        self._prefs._app._settings.language = values[idx]
        self._save()

    def onAutostartChanged_(self, sender):
        from ohmyvoice.autostart import enable, disable

        on = sender.state() == 1
        self._prefs._app._settings.autostart = on
        if on:
            enable()
        else:
            disable()
        self._save()

    def onNotificationChanged_(self, sender):
        self._prefs._app._settings.notification_on_complete = sender.state() == 1
        self._save()

    def onHistoryLimitChanged_(self, sender):
        val = sender.integerValue()
        if 100 <= val <= 5000:
            self._prefs._app._settings.history_max_entries = val
            self._save()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preferences.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/preferences.py tests/test_preferences.py
git commit -m "feat: general tab with hotkey display, behavior switches, history limit"
```

---

### Task 3: Audio tab

**Files:**
- Modify: `src/ohmyvoice/preferences.py`
- Modify: `tests/test_preferences.py`

- [ ] **Step 1: Add tests for audio tab**

Append to `tests/test_preferences.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preferences.py::test_audio_tab_has_mic_popup -v`
Expected: `AttributeError`

- [ ] **Step 3: Implement `_build_audio_view`**

Add to `PreferencesWindow.__init__`:

```python
self._mic_popup = None
self._sound_switch = None
self._recording_slider = None
self._recording_value_label = None
```

Add import for `NSSlider`.

Replace `_build_audio_view` placeholder:

```python
def _build_audio_view(self):
    s = self._app._settings
    view = _FlippedView.alloc().initWithFrame_(
        NSMakeRect(0, 0, _WINDOW_WIDTH, 0)
    )
    y = 20

    # --- Input section ---
    y = self._section_header(view, "输入", y)
    box = self._group_box(view, y, _ROW_H)

    self._mic_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(0, 0, 200, 25), False
    )
    self._populate_mic_list()
    self._mic_popup.setTarget_(self._action_delegate)
    self._mic_popup.setAction_("onMicChanged:")
    self._row_in_group(box, "麦克风", self._mic_popup, 0)

    y += _ROW_H + _SECTION_GAP

    # --- Feedback section ---
    y = self._section_header(view, "反馈", y)
    box = self._group_box(view, y, _ROW_H_SUB)

    self._sound_switch = NSSwitch.alloc().initWithFrame_(
        NSMakeRect(0, 0, 38, 22)
    )
    self._sound_switch.setState_(1 if s.sound_feedback else 0)
    self._sound_switch.setTarget_(self._action_delegate)
    self._sound_switch.setAction_("onSoundFeedbackChanged:")

    lbl = NSTextField.labelWithString_("提示音")
    lbl.setFont_(NSFont.systemFontOfSize_(13))
    lbl.setFrame_(NSMakeRect(_INNER_PAD, 6, 200, 17))
    box.addSubview_(lbl)
    sub = NSTextField.labelWithString_("录音开始和转写完成时播放")
    sub.setFont_(NSFont.systemFontOfSize_(11))
    sub.setTextColor_(NSColor.secondaryLabelColor())
    sub.setFrame_(NSMakeRect(_INNER_PAD, 24, 260, 14))
    box.addSubview_(sub)
    sw_w = self._sound_switch.frame().size.width
    self._sound_switch.setFrame_(NSMakeRect(
        _CONTENT_W - _INNER_PAD - sw_w, (_ROW_H_SUB - 22) // 2, sw_w, 22
    ))
    box.addSubview_(self._sound_switch)

    y += _ROW_H_SUB + _SECTION_GAP

    # --- Recording section ---
    y = self._section_header(view, "录音", y)
    box = self._group_box(view, y, _ROW_H)

    self._recording_slider = NSSlider.alloc().initWithFrame_(
        NSMakeRect(0, 0, 130, 22)
    )
    self._recording_slider.setMinValue_(10)
    self._recording_slider.setMaxValue_(120)
    self._recording_slider.setIntegerValue_(s.max_recording_seconds)
    self._recording_slider.setContinuous_(True)
    self._recording_slider.setTarget_(self._action_delegate)
    self._recording_slider.setAction_("onRecordingSliderChanged:")

    self._recording_value_label = NSTextField.labelWithString_(
        f"{s.max_recording_seconds} 秒"
    )
    self._recording_value_label.setFont_(NSFont.systemFontOfSize_(12))
    self._recording_value_label.setTextColor_(NSColor.secondaryLabelColor())
    self._recording_value_label.setAlignment_(2)  # Right

    combo = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 180, 22))
    self._recording_slider.setFrame_(NSMakeRect(0, 0, 130, 22))
    self._recording_value_label.setFrame_(NSMakeRect(138, 2, 42, 17))
    combo.addSubview_(self._recording_slider)
    combo.addSubview_(self._recording_value_label)

    self._row_in_group(box, "最长录音时间", combo, 0)

    y += _ROW_H + 20
    view.setFrame_(NSMakeRect(0, 0, _WINDOW_WIDTH, y))
    return view

def _populate_mic_list(self):
    """Fill the mic popup with available input devices."""
    self._mic_popup.removeAllItems()
    self._mic_popup.addItemWithTitle_("系统默认")
    self._mic_devices = [None]  # index → device name or None

    try:
        from ohmyvoice.recorder import Recorder

        devices = Recorder.list_input_devices()
        for d in devices:
            self._mic_popup.addItemWithTitle_(d["name"])
            self._mic_devices.append(d["name"])
    except Exception:
        pass

    # Select current device
    current = self._app._settings.input_device
    if current and current in self._mic_devices:
        idx = self._mic_devices.index(current)
        self._mic_popup.selectItemAtIndex_(idx)
    else:
        self._mic_popup.selectItemAtIndex_(0)

def _refresh_audio_devices(self):
    """Re-populate mic list (called on tab switch to audio)."""
    if self._mic_popup is not None:
        self._populate_mic_list()
```

Add to `_switch_tab`, before setting content view:

```python
if tab_id == "audio":
    self._refresh_audio_devices()
```

Add to `_ActionDelegate`:

```python
# --- Audio tab ---

def onMicChanged_(self, sender):
    idx = sender.indexOfSelectedItem()
    devices = self._prefs._mic_devices
    device = devices[idx] if idx < len(devices) else None
    self._prefs._app._settings.input_device = device
    self._save()
    # Rebuild Recorder with new device
    from ohmyvoice.recorder import Recorder

    self._prefs._app._recorder = Recorder(
        sample_rate=16000, device=device
    )

def onSoundFeedbackChanged_(self, sender):
    self._prefs._app._settings.sound_feedback = sender.state() == 1
    self._save()

def onRecordingSliderChanged_(self, sender):
    val = int(sender.integerValue())
    self._prefs._app._settings.max_recording_seconds = val
    self._prefs._recording_value_label.setStringValue_(f"{val} 秒")
    self._save()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preferences.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/preferences.py tests/test_preferences.py
git commit -m "feat: audio tab with mic selection, sound feedback, recording limit"
```

---

### Task 4: Recognition tab

**Files:**
- Modify: `src/ohmyvoice/preferences.py`
- Modify: `tests/test_preferences.py`

- [ ] **Step 1: Add tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preferences.py::test_recognition_tab_template_popup -v`
Expected: `AttributeError`

- [ ] **Step 3: Implement `_build_recognition_view`**

Add to `PreferencesWindow.__init__`:

```python
self._template_popup = None
self._prompt_textview = None
self._quant_popup = None
```

Add imports for `NSScrollView, NSTextView`.

Replace `_build_recognition_view` placeholder:

```python
def _build_recognition_view(self):
    s = self._app._settings
    view = _FlippedView.alloc().initWithFrame_(
        NSMakeRect(0, 0, _WINDOW_WIDTH, 0)
    )
    y = 20

    # --- Prompt section ---
    y = self._section_header(view, "PROMPT 模板", y)
    box = self._group_box(view, y, _ROW_H)

    _TEMPLATE_OPTIONS = ["编程", "会议", "日常", "自定义"]
    _TEMPLATE_VALUES = ["coding", "meeting", "general", "custom"]
    self._template_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(0, 0, 100, 25), False
    )
    self._template_popup.addItemsWithTitles_(_TEMPLATE_OPTIONS)
    tidx = (
        _TEMPLATE_VALUES.index(s.active_prompt_template)
        if s.active_prompt_template in _TEMPLATE_VALUES
        else 0
    )
    self._template_popup.selectItemAtIndex_(tidx)
    self._template_popup.setTarget_(self._action_delegate)
    self._template_popup.setAction_("onTemplateChanged:")
    self._row_in_group(box, "当前模板", self._template_popup, 0)
    y += _ROW_H

    # Prompt text view
    text_h = 90
    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(_PADDING, y + 4, _CONTENT_W, text_h)
    )
    self._prompt_textview = NSTextView.alloc().initWithFrame_(
        NSMakeRect(0, 0, _CONTENT_W - 4, text_h)
    )
    self._prompt_textview.setFont_(
        NSFont.monospacedSystemFontOfSize_weight_(12, 0.0)
    )
    prompt_text = s.get_active_prompt()
    self._prompt_textview.setString_(prompt_text)

    is_custom = s.active_prompt_template == "custom"
    self._prompt_textview.setEditable_(is_custom)
    if not is_custom:
        self._prompt_textview.setBackgroundColor_(
            NSColor.controlBackgroundColor()
        )
    self._prompt_textview.setDelegate_(self._action_delegate)

    scroll.setDocumentView_(self._prompt_textview)
    scroll.setHasVerticalScroller_(True)
    scroll.setBorderType_(3)  # NSBezelBorder
    view.addSubview_(scroll)
    y += text_h + 8

    # Hint
    hint = NSTextField.labelWithString_(
        "选择"自定义"后可编辑内容，预设模板仅供预览"
    )
    hint.setFont_(NSFont.systemFontOfSize_(11))
    hint.setTextColor_(NSColor.tertiaryLabelColor())
    hint.setFrame_(NSMakeRect(_PADDING, y, _CONTENT_W, 14))
    view.addSubview_(hint)
    y += 14 + _SECTION_GAP

    # --- Model section ---
    y = self._section_header(view, "模型", y)
    quant_box_h = _ROW_H + 26  # Extra space for warning text
    box = self._group_box(view, y, quant_box_h)

    _QUANT_OPTIONS = ["4-bit", "8-bit"]
    _QUANT_VALUES = ["4bit", "8bit"]
    self._quant_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(0, 0, 80, 25), False
    )
    self._quant_popup.addItemsWithTitles_(_QUANT_OPTIONS)
    qidx = (
        _QUANT_VALUES.index(s.model_quantization)
        if s.model_quantization in _QUANT_VALUES
        else 0
    )
    self._quant_popup.selectItemAtIndex_(qidx)
    self._quant_popup.setTarget_(self._action_delegate)
    self._quant_popup.setAction_("onQuantChanged:")
    self._row_in_group(box, "量化精度", self._quant_popup, 0)

    warn = NSTextField.labelWithString_(
        "⚠ 切换精度需要重新加载模型（约 5 秒）"
    )
    warn.setFont_(NSFont.systemFontOfSize_(11))
    warn.setTextColor_(NSColor.systemOrangeColor())
    warn.setFrame_(NSMakeRect(_INNER_PAD, _ROW_H + 4, _CONTENT_W - 2 * _INNER_PAD, 14))
    box.addSubview_(warn)

    y += quant_box_h + 20
    view.setFrame_(NSMakeRect(0, 0, _WINDOW_WIDTH, y))
    return view
```

Add to `_ActionDelegate`:

```python
# --- Recognition tab ---

_TEMPLATE_VALUES = ["coding", "meeting", "general", "custom"]

def onTemplateChanged_(self, sender):
    idx = sender.indexOfSelectedItem()
    val = self._TEMPLATE_VALUES[idx]
    s = self._prefs._app._settings
    s.active_prompt_template = val
    self._save()
    # Update text view content and editability
    tv = self._prefs._prompt_textview
    if val == "custom":
        tv.setString_(s.custom_prompt)
        tv.setEditable_(True)
        tv.setBackgroundColor_(NSColor.textBackgroundColor())
    else:
        tv.setString_(s.get_active_prompt())
        tv.setEditable_(False)
        tv.setBackgroundColor_(NSColor.controlBackgroundColor())

def onQuantChanged_(self, sender):
    import threading

    _QUANT_VALUES = ["4bit", "8bit"]
    idx = sender.indexOfSelectedItem()
    val = _QUANT_VALUES[idx]
    s = self._prefs._app._settings
    if val == s.model_quantization:
        return
    s.model_quantization = val
    self._save()
    engine = self._prefs._app._engine
    app = self._prefs._app

    def _reload():
        engine.unload()
        bits = int(val.replace("bit", ""))
        engine.load(quantize_bits=bits)
        if hasattr(app, "menu") and "状态: 加载中..." in app.menu:
            app.menu["状态: 加载中..."].title = (
                f"就绪 · {s.hotkey_display}"
            )

    if hasattr(app, "menu"):
        for key in app.menu:
            if "就绪" in str(app.menu[key].title if hasattr(app.menu[key], 'title') else ''):
                app.menu[key].title = "状态: 加载中..."
                break
    threading.Thread(target=_reload, daemon=True).start()
```

Add NSTextView delegate method for saving custom prompt on edit:

```python
def textDidChange_(self, notification):
    """Called when prompt text view content changes."""
    tv = notification.object()
    s = self._prefs._app._settings
    if s.active_prompt_template == "custom":
        s.custom_prompt = tv.string()
        self._save()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preferences.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/preferences.py tests/test_preferences.py
git commit -m "feat: recognition tab with prompt templates and quantization control"
```

---

### Task 5: About tab

**Files:**
- Modify: `src/ohmyvoice/preferences.py`
- Modify: `tests/test_preferences.py`

- [ ] **Step 1: Add test**

```python
def test_about_tab_shows_app_name(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    pw._switch_tab("about")
    # Verify the about view exists and has content
    view = pw._views["about"]
    assert view.frame().size.height > 100
```

- [ ] **Step 2: Run test to verify it fails**

Already passes with placeholder (height 260). Change test to check for name label:

```python
def test_about_tab_shows_app_name(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._app_name_label is not None
    assert pw._app_name_label.stringValue() == "OhMyVoice"
```

Run: `python -m pytest tests/test_preferences.py::test_about_tab_shows_app_name -v`
Expected: `AttributeError`

- [ ] **Step 3: Implement `_build_about_view`**

Add to `PreferencesWindow.__init__`:

```python
self._app_name_label = None
```

Add imports: `NSWorkspace, NSURL`.

Replace `_build_about_view` placeholder:

```python
def _build_about_view(self):
    s = self._app._settings
    view = _FlippedView.alloc().initWithFrame_(
        NSMakeRect(0, 0, _WINDOW_WIDTH, 0)
    )
    y = 24

    # --- App header (centered) ---
    # App icon
    icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
        "mic.fill", "OhMyVoice"
    )
    icon_view = NSImageView.alloc().initWithFrame_(
        NSMakeRect((_WINDOW_WIDTH - 48) // 2, y, 48, 48)
    )
    if icon:
        icon_view.setImage_(icon)
    icon_view.setContentTintColor_(NSColor.controlAccentColor())
    view.addSubview_(icon_view)
    y += 56

    self._app_name_label = NSTextField.labelWithString_("OhMyVoice")
    self._app_name_label.setFont_(NSFont.systemFontOfSize_weight_(18, 0.5))
    self._app_name_label.setAlignment_(1)  # Center
    self._app_name_label.setFrame_(NSMakeRect(0, y, _WINDOW_WIDTH, 22))
    view.addSubview_(self._app_name_label)
    y += 24

    from ohmyvoice import __version__

    version_label = NSTextField.labelWithString_(f"版本 {__version__}")
    version_label.setFont_(NSFont.systemFontOfSize_(12))
    version_label.setTextColor_(NSColor.secondaryLabelColor())
    version_label.setAlignment_(1)
    version_label.setFrame_(NSMakeRect(0, y, _WINDOW_WIDTH, 16))
    view.addSubview_(version_label)
    y += 28

    # --- Model section ---
    y = self._section_header(view, "模型", y)
    model_h = _ROW_H * 2
    box = self._group_box(view, y, model_h)
    ry = 0

    # Model name + status
    quant = s.model_quantization
    model_text = f"{s.model_name} ({quant})"

    engine = self._app._engine
    if engine and engine.is_loaded:
        status_text = "已加载"
        status_color = NSColor.systemGreenColor()
    else:
        status_text = "未加载"
        status_color = NSColor.secondaryLabelColor()

    status_label = NSTextField.labelWithString_(status_text)
    status_label.setFont_(NSFont.systemFontOfSize_(12))
    status_label.setTextColor_(status_color)
    status_label.setFrame_(NSMakeRect(0, 0, 60, 17))
    ry = self._row_in_group(box, model_text, status_label, ry)
    self._separator_in_group(box, ry)

    # Disk usage
    cache_dir = _cache_dir_for_display(s)
    size_text = _dir_size_str(cache_dir)
    size_label = NSTextField.labelWithString_(size_text)
    size_label.setFont_(NSFont.systemFontOfSize_(12))
    size_label.setTextColor_(NSColor.secondaryLabelColor())
    size_label.setFrame_(NSMakeRect(0, 0, 60, 17))
    ry = self._row_in_group(box, "磁盘占用", size_label, ry)

    y += model_h + _SECTION_GAP

    # --- Links section ---
    y = self._section_header(view, "链接", y)
    links_h = _ROW_H * 2
    box = self._group_box(view, y, links_h)

    gh_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 40, 17))
    gh_btn.setTitle_("打开")
    gh_btn.setBordered_(False)
    gh_btn.setFont_(NSFont.systemFontOfSize_(13))
    gh_btn.setContentTintColor_(NSColor.linkColor())
    gh_btn.setTarget_(self._action_delegate)
    gh_btn.setAction_("onOpenGitHub:")
    self._row_in_group(box, "GitHub 项目主页", gh_btn, 0)
    self._separator_in_group(box, _ROW_H)

    fb_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 40, 17))
    fb_btn.setTitle_("打开")
    fb_btn.setBordered_(False)
    fb_btn.setFont_(NSFont.systemFontOfSize_(13))
    fb_btn.setContentTintColor_(NSColor.linkColor())
    fb_btn.setTarget_(self._action_delegate)
    fb_btn.setAction_("onOpenFeedback:")
    self._row_in_group(box, "反馈与建议", fb_btn, _ROW_H)

    y += links_h + 20
    view.setFrame_(NSMakeRect(0, 0, _WINDOW_WIDTH, y))
    return view
```

Add helper functions at module level:

```python
from pathlib import Path as _Path

def _cache_dir_for_display(settings):
    """Get the model cache directory path."""
    name = settings.model_name.replace("/", "--").lower()
    quant = settings.model_quantization
    return _Path.home() / ".cache" / "ohmyvoice" / "models" / f"{name}-{quant}"

def _dir_size_str(path):
    """Human-readable size of a directory."""
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
```

Add import for `NSImageView`.

Add to `_ActionDelegate`:

```python
# --- About tab ---

def onOpenGitHub_(self, sender):
    NSWorkspace.sharedWorkspace().openURL_(
        NSURL.URLWithString_("https://github.com/user/ohmyvoice")
    )

def onOpenFeedback_(self, sender):
    NSWorkspace.sharedWorkspace().openURL_(
        NSURL.URLWithString_("https://github.com/user/ohmyvoice/issues")
    )
```

**Note:** Replace `user/ohmyvoice` with the actual GitHub URL when known.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preferences.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/preferences.py tests/test_preferences.py
git commit -m "feat: about tab with model status, disk usage, and links"
```

---

### Task 6: Hotkey recorder + HotkeyManager pause/resume

**Files:**
- Modify: `src/ohmyvoice/hotkey.py` (add `pause` / `resume`)
- Modify: `src/ohmyvoice/preferences.py` (add hotkey capture)
- Modify: `tests/test_preferences.py`

- [ ] **Step 1: Add test for pause/resume**

```python
# In tests/test_preferences.py

def test_hotkey_manager_pause_resume():
    """pause/resume methods exist and don't crash when no tap is active."""
    from ohmyvoice.hotkey import HotkeyManager

    hm = HotkeyManager(
        modifiers=["option"], key="space",
        on_press=lambda: None, on_release=lambda: None,
    )
    # Should not raise even without an active tap
    hm.pause()
    hm.resume()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_preferences.py::test_hotkey_manager_pause_resume -v`
Expected: `AttributeError: 'HotkeyManager' object has no attribute 'pause'`

- [ ] **Step 3: Add pause/resume to HotkeyManager**

Add to `src/ohmyvoice/hotkey.py` in the `HotkeyManager` class, after the `update_hotkey` method:

```python
def pause(self):
    """Temporarily disable the event tap (e.g., during hotkey capture)."""
    if self._tap:
        Quartz.CGEventTapEnable(self._tap, False)

def resume(self):
    """Re-enable the event tap after pause."""
    if self._tap:
        Quartz.CGEventTapEnable(self._tap, True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_preferences.py::test_hotkey_manager_pause_resume -v`
Expected: PASS

- [ ] **Step 5: Add hotkey capture test**

```python
def test_hotkey_capture_starts(mock_app):
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    pw._build()
    assert pw._record_btn is not None
    # Simulate starting capture
    pw._start_hotkey_capture()
    assert pw._record_btn.title() == "按下新组合..."
    pw._cancel_hotkey_capture()
    assert pw._record_btn.title() == "录制"
```

- [ ] **Step 6: Implement hotkey capture in preferences.py**

Add to `PreferencesWindow.__init__`:

```python
self._key_monitor = None
```

Add methods to `PreferencesWindow`:

```python
def _start_hotkey_capture(self):
    """Enter hotkey capture mode."""
    from AppKit import NSEvent, NSEventMaskKeyDown

    # Pause global hotkey to avoid interference
    if self._app._hotkey:
        self._app._hotkey.pause()

    self._record_btn.setTitle_("按下新组合...")
    self._record_btn.setEnabled_(False)

    def handler(event):
        flags = event.modifierFlags()
        keycode = event.keyCode()
        mods = self._flags_to_modifiers(flags)
        key = self._keycode_to_name(keycode)
        if key and mods:
            self._finish_hotkey_capture(mods, key)
        return event

    self._key_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        NSEventMaskKeyDown, handler
    )

def _finish_hotkey_capture(self, modifiers, key):
    """Apply captured hotkey and exit capture mode."""
    from AppKit import NSEvent

    if self._key_monitor:
        NSEvent.removeMonitor_(self._key_monitor)
        self._key_monitor = None

    s = self._app._settings
    s.hotkey_modifiers = modifiers
    s.hotkey_key = key
    s.save()

    self._hotkey_label.setStringValue_(s.hotkey_display)
    self._record_btn.setTitle_("录制")
    self._record_btn.setEnabled_(True)

    if self._app._hotkey:
        self._app._hotkey.update_hotkey(modifiers, key)
        self._app._hotkey.resume()

def _cancel_hotkey_capture(self):
    """Exit capture mode without changes."""
    from AppKit import NSEvent

    if self._key_monitor:
        NSEvent.removeMonitor_(self._key_monitor)
        self._key_monitor = None

    self._record_btn.setTitle_("录制")
    self._record_btn.setEnabled_(True)

    if self._app._hotkey:
        self._app._hotkey.resume()

@staticmethod
def _flags_to_modifiers(flags):
    """Convert NSEvent modifier flags to list of modifier names."""
    result = []
    if flags & (1 << 20):  # NSEventModifierFlagCommand
        result.append("command")
    if flags & (1 << 17):  # NSEventModifierFlagShift
        result.append("shift")
    if flags & (1 << 19):  # NSEventModifierFlagOption
        result.append("option")
    if flags & (1 << 18):  # NSEventModifierFlagControl
        result.append("control")
    return result

@staticmethod
def _keycode_to_name(keycode):
    """Convert macOS keycode to key name string."""
    from ohmyvoice.hotkey import _KEY_CODES
    for name, code in _KEY_CODES.items():
        if code == keycode:
            return name
    return None
```

Update the record button setup in `_build_general_view` to use `_start_hotkey_capture`:

```python
self._record_btn.setTarget_(self._action_delegate)
self._record_btn.setAction_("onRecordHotkey:")
```

Add to `_ActionDelegate`:

```python
def onRecordHotkey_(self, sender):
    self._prefs._start_hotkey_capture()
```

- [ ] **Step 7: Run all tests**

Run: `python -m pytest tests/test_preferences.py -v`
Expected: All 15 tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/ohmyvoice/hotkey.py src/ohmyvoice/preferences.py tests/test_preferences.py
git commit -m "feat: hotkey recorder with HotkeyManager pause/resume"
```

---

### Task 7: Wire to app.py + fix quantization startup bug

**Files:**
- Modify: `src/ohmyvoice/app.py`
- Modify: `tests/test_preferences.py`

- [ ] **Step 1: Add integration test**

```python
def test_app_creates_preferences_on_settings(mock_app):
    """Verify PreferencesWindow is instantiated lazily."""
    from ohmyvoice.preferences import PreferencesWindow

    pw = PreferencesWindow(mock_app)
    assert pw._window is None
    pw._build()
    assert pw._window is not None
```

- [ ] **Step 2: Modify app.py**

In `src/ohmyvoice/app.py`:

1. Add import at top:

```python
from ohmyvoice.preferences import PreferencesWindow
```

2. In `OhMyVoiceApp.__init__`, add after existing attributes:

```python
self._prefs_window = None
```

3. Replace `_on_settings` method:

```python
def _on_settings(self, _):
    if self._prefs_window is None:
        self._prefs_window = PreferencesWindow(self)
    self._prefs_window.show()
```

4. Fix `_load_model_async` to use quantization setting — change the `_load` inner function:

```python
def _load():
    try:
        bits = int(self._settings.model_quantization.replace("bit", ""))
        self._engine.load(quantize_bits=bits)
        self._set_state("idle")
        self.menu[
            "状态: 加载中..."
        ].title = f"就绪 · {self._settings.hotkey_display}"
        self._start_hotkey()
    except Exception as e:
        self.menu["状态: 加载中..."].title = f"模型加载失败: {e}"
```

5. Delete the old `_on_settings` rumps.Window implementation (lines 160-183 in current app.py).

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (including existing test_settings.py, test_history.py, etc.)

- [ ] **Step 4: Verify no import errors**

Run: `python -c "from ohmyvoice.preferences import PreferencesWindow; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/app.py src/ohmyvoice/preferences.py tests/test_preferences.py
git commit -m "feat: wire PreferencesWindow to app, fix quantization on startup"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Window + toolbar + tab switching | `preferences.py`, `test_preferences.py` (new) |
| 2 | Form helpers + General tab | `preferences.py`, `test_preferences.py` |
| 3 | Audio tab | `preferences.py`, `test_preferences.py` |
| 4 | Recognition tab | `preferences.py`, `test_preferences.py` |
| 5 | About tab | `preferences.py`, `test_preferences.py` |
| 6 | Hotkey recorder + pause/resume | `preferences.py`, `hotkey.py`, `test_preferences.py` |
| 7 | Wire to app.py + quantization fix | `app.py`, `test_preferences.py` |

Total: 7 tasks, ~15 tests, 3 files created/modified.
