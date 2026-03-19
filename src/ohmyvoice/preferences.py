"""macOS native preferences window with 4 toolbar tabs."""

import objc
from pathlib import Path as _Path

from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSBox,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSImageView,
    NSObject,
    NSPopUpButton,
    NSScrollView,
    NSSlider,
    NSSwitch,
    NSTextField,
    NSTextView,
    NSToolbar,
    NSToolbarItem,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
    NSWorkspace,
)
from Foundation import NSURL, NSMakeRect, NSMakeSize

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

_PADDING = 24
_CONTENT_W = _WINDOW_WIDTH - 2 * _PADDING  # 472
_ROW_H = 36
_ROW_H_SUB = 48   # Row with sublabel
_SECTION_GAP = 16
_INNER_PAD = 14

_LANGUAGE_OPTIONS = ["自动检测", "中文为主", "英文为主"]
_LANGUAGE_VALUES = ["auto", "zh", "en"]

_TEMPLATE_OPTIONS = ["编程", "会议", "日常", "自定义"]
_TEMPLATE_VALUES = ["coding", "meeting", "general", "custom"]

_QUANT_OPTIONS = ["4-bit", "8-bit"]
_QUANT_VALUES = ["4bit", "8bit"]


class _FlippedView(NSView):
    """NSView with top-left origin (y increases downward)."""

    def isFlipped(self):
        return True


class _ToolbarDelegate(NSObject):
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


class _ActionDelegate(NSObject):
    """Handles target-action callbacks from controls in the General tab."""

    def init(self):
        self = objc.super(_ActionDelegate, self).init()
        if self is None:
            return None
        self._prefs = None
        return self

    def onLanguageChanged_(self, sender):
        if self._prefs is None:
            return
        idx = sender.indexOfSelectedItem()
        lang = _LANGUAGE_VALUES[idx] if 0 <= idx < len(_LANGUAGE_VALUES) else "auto"
        settings = self._prefs._app._settings
        settings.language = lang
        settings.save()

    def onAutostartChanged_(self, sender):
        if self._prefs is None:
            return
        enabled = bool(sender.state())
        settings = self._prefs._app._settings
        settings.autostart = enabled
        settings.save()
        from ohmyvoice import autostart
        if enabled:
            autostart.enable()
        else:
            autostart.disable()

    def onNotificationChanged_(self, sender):
        if self._prefs is None:
            return
        settings = self._prefs._app._settings
        settings.notification_on_complete = bool(sender.state())
        settings.save()

    def onHistoryLimitChanged_(self, sender):
        if self._prefs is None:
            return
        val = sender.integerValue()
        if 100 <= val <= 5000:
            self._prefs._app._settings.history_max_entries = val
            self._prefs._app._settings.save()

    def onRecordHotkey_(self, sender):
        if self._prefs is not None:
            self._prefs._start_hotkey_capture()

    def onMicChanged_(self, sender):
        if self._prefs is None:
            return
        idx = sender.indexOfSelectedItem()
        devices = self._prefs._mic_devices
        device = devices[idx] if idx < len(devices) else None
        self._prefs._app._settings.input_device = device
        self._prefs._app._settings.save()
        try:
            from ohmyvoice.recorder import Recorder
            self._prefs._app._recorder = Recorder(sample_rate=16000, device=device)
        except Exception:
            pass

    def onSoundFeedbackChanged_(self, sender):
        if self._prefs is None:
            return
        self._prefs._app._settings.sound_feedback = sender.state() == 1
        self._prefs._app._settings.save()

    def onRecordingSliderChanged_(self, sender):
        if self._prefs is None:
            return
        val = int(sender.integerValue())
        self._prefs._app._settings.max_recording_seconds = val
        self._prefs._recording_value_label.setStringValue_(f"{val} 秒")
        self._prefs._app._settings.save()

    def onTemplateChanged_(self, sender):
        if self._prefs is None:
            return
        idx = sender.indexOfSelectedItem()
        val = _TEMPLATE_VALUES[idx] if 0 <= idx < len(_TEMPLATE_VALUES) else "coding"
        s = self._prefs._app._settings
        s.active_prompt_template = val
        s.save()
        tv = self._prefs._prompt_textview
        if tv is None:
            return
        if val == "custom":
            tv.setString_(s.custom_prompt)
            tv.setEditable_(True)
            tv.setBackgroundColor_(NSColor.textBackgroundColor())
        else:
            tv.setString_(s.get_active_prompt())
            tv.setEditable_(False)
            tv.setBackgroundColor_(NSColor.controlBackgroundColor())

    def onQuantChanged_(self, sender):
        if self._prefs is None:
            return
        import threading
        idx = sender.indexOfSelectedItem()
        val = _QUANT_VALUES[idx] if 0 <= idx < len(_QUANT_VALUES) else "4bit"
        s = self._prefs._app._settings
        if val == s.model_quantization:
            return
        s.model_quantization = val
        s.save()
        engine = self._prefs._app._engine
        def _reload():
            try:
                engine.unload()
                bits = int(val.replace("bit", ""))
                engine.load(quantize_bits=bits)
            except Exception as e:
                print(f"Model reload failed: {e}")
        threading.Thread(target=_reload, daemon=True).start()

    def textDidChange_(self, notification):
        if self._prefs is None:
            return
        tv = notification.object()
        s = self._prefs._app._settings
        if s.active_prompt_template == "custom":
            s.custom_prompt = tv.string()
            s.save()

    def onOpenGitHub_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(
            NSURL.URLWithString_("https://github.com/user/ohmyvoice")
        )

    def onOpenFeedback_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(
            NSURL.URLWithString_("https://github.com/user/ohmyvoice/issues")
        )


class PreferencesWindow:
    """NSWindow-based preferences with 4 toolbar tabs."""

    def __init__(self, app):
        self._app = app
        self._window = None
        self._toolbar_delegate = None
        self._views = {}
        self._current_tab = None
        # General tab control references
        self._hotkey_label = None
        self._record_btn = None
        self._language_popup = None
        self._autostart_switch = None
        self._notification_switch = None
        self._history_limit_field = None
        # Audio tab control references
        self._mic_popup = None
        self._mic_devices = [None]
        self._sound_switch = None
        self._recording_slider = None
        self._recording_value_label = None
        # Recognition tab control references
        self._template_popup = None
        self._prompt_textview = None
        self._quant_popup = None
        # About tab control references
        self._app_name_label = None
        # Hotkey capture state
        self._key_monitor = None
        self._action_delegate = _ActionDelegate.alloc().init()
        self._action_delegate._prefs = self

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
        if tab_id == "audio":
            self._refresh_audio_devices()
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

    # ------------------------------------------------------------------ helpers

    def _section_header(self, parent, text, y):
        """Small uppercase section label."""
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(_PADDING, y, _CONTENT_W, 16)
        )
        label.setStringValue_(text.upper())
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(NSFont.systemFontOfSize_(10))
        label.setTextColor_(NSColor.secondaryLabelColor())
        parent.addSubview_(label)
        return y + 16

    def _group_box(self, parent, y, height):
        """Rounded background box for grouped rows."""
        box = NSBox.alloc().initWithFrame_(
            NSMakeRect(_PADDING, y, _CONTENT_W, height)
        )
        box.setBoxType_(4)  # NSBoxCustom
        box.setFillColor_(NSColor.controlBackgroundColor())
        box.setBorderColor_(NSColor.separatorColor())
        box.setCornerRadius_(8)
        box.setBorderWidth_(0.5)
        box.setContentViewMargins_(NSMakeSize(0, 0))
        box.setTitle_("")
        parent.addSubview_(box)
        return box

    def _row_in_group(self, group, label_text, control, row_y, sublabel=None):
        """Place a label + control inside a group box."""
        row_h = _ROW_H_SUB if sublabel else _ROW_H
        group_h = int(group.frame().size.height)

        # Label
        lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(_INNER_PAD, row_y, 180, 18)
        )
        lbl.setStringValue_(label_text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setFont_(NSFont.systemFontOfSize_(13))
        group.addSubview_(lbl)

        if sublabel:
            sub = NSTextField.alloc().initWithFrame_(
                NSMakeRect(_INNER_PAD, row_y + 20, 200, 14)
            )
            sub.setStringValue_(sublabel)
            sub.setBezeled_(False)
            sub.setDrawsBackground_(False)
            sub.setEditable_(False)
            sub.setSelectable_(False)
            sub.setFont_(NSFont.systemFontOfSize_(11))
            sub.setTextColor_(NSColor.secondaryLabelColor())
            group.addSubview_(sub)

        # Place control on the right side
        ctrl_frame = control.frame()
        ctrl_w = ctrl_frame.size.width
        ctrl_h = ctrl_frame.size.height
        ctrl_x = _CONTENT_W - _INNER_PAD - ctrl_w
        ctrl_y = row_y + (row_h - ctrl_h) / 2
        control.setFrameOrigin_(_make_point(ctrl_x, ctrl_y))
        group.addSubview_(control)
        return row_y + row_h

    def _separator_in_group(self, group, y):
        """1px horizontal separator line inside a group."""
        sep = NSBox.alloc().initWithFrame_(
            NSMakeRect(_INNER_PAD, y, _CONTENT_W - 2 * _INNER_PAD, 1)
        )
        sep.setBoxType_(2)  # NSBoxSeparator
        group.addSubview_(sep)
        return sep

    # ------------------------------------------------------------------ tabs

    def _build_general_view(self):
        settings = self._app._settings
        y = _PADDING  # cursor from top (flipped view)

        # ---- 快捷键 section ----
        sec1_label_h = 16
        sec1_rows = 1
        sec1_group_h = _ROW_H_SUB + 2 * _INNER_PAD  # one row with sublabel

        # ---- 行为 section ----
        sec2_rows = 3
        sec2_group_h = _ROW_H * sec2_rows + _SECTION_GAP  # rows + inner spacing
        # actual: INNER_PAD top + ROW_H * 3 + 2 separators + INNER_PAD bottom
        sec2_group_h = _INNER_PAD + _ROW_H * 3 + 2 * 1 + _INNER_PAD

        # ---- 数据 section ----
        sec3_group_h = _INNER_PAD + _ROW_H + _INNER_PAD

        total_h = (
            _PADDING                        # top
            + sec1_label_h + 6             # section header + gap
            + sec1_group_h + _SECTION_GAP  # group + gap
            + sec1_label_h + 6             # section header + gap
            + sec2_group_h + _SECTION_GAP  # group + gap
            + sec1_label_h + 6             # section header + gap
            + sec3_group_h
            + _PADDING                     # bottom
        )

        view = _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, total_h)
        )

        # -- 快捷键 --
        self._section_header(view, "快捷键", y)
        y += sec1_label_h + 6

        box1 = self._group_box(view, y, sec1_group_h)
        # Compound control: hotkey badge + record button in an HStack view
        badge_w, badge_h = 90, 24
        btn_w, btn_h = 52, 24
        compound_w = badge_w + 8 + btn_w
        compound_h = max(badge_h, btn_h)

        compound = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, compound_w, compound_h)
        )

        hotkey_text = settings.hotkey_display
        badge = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, (compound_h - badge_h) / 2, badge_w, badge_h)
        )
        badge.setStringValue_(hotkey_text)
        badge.setBezeled_(True)
        badge.setDrawsBackground_(True)
        badge.setEditable_(False)
        badge.setSelectable_(False)
        badge.setAlignment_(1)  # NSTextAlignmentCenter
        badge.setFont_(NSFont.monospacedSystemFontOfSize_weight_(13, 0))
        compound.addSubview_(badge)
        self._hotkey_label = badge

        rec_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(badge_w + 8, (compound_h - btn_h) / 2, btn_w, btn_h)
        )
        rec_btn.setTitle_("录制")
        rec_btn.setBezelStyle_(4)  # NSBezelStyleRounded
        rec_btn.setTarget_(self._action_delegate)
        rec_btn.setAction_("onRecordHotkey:")
        compound.addSubview_(rec_btn)
        self._record_btn = rec_btn

        self._row_in_group(
            box1, "快捷键", compound,
            _INNER_PAD,
            sublabel="按住录音，松开转写",
        )
        y += sec1_group_h + _SECTION_GAP

        # -- 行为 --
        self._section_header(view, "行为", y)
        y += sec1_label_h + 6

        box2 = self._group_box(view, y, sec2_group_h)
        row_y = _INNER_PAD

        # Language popup
        popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(0, 0, 130, 26))
        for opt in _LANGUAGE_OPTIONS:
            popup.addItemWithTitle_(opt)
        current_lang = settings.language
        sel_idx = _LANGUAGE_VALUES.index(current_lang) if current_lang in _LANGUAGE_VALUES else 0
        popup.selectItemAtIndex_(sel_idx)
        popup.setTarget_(self._action_delegate)
        popup.setAction_("onLanguageChanged:")
        self._language_popup = popup
        self._row_in_group(box2, "语言", popup, row_y)
        row_y += _ROW_H

        self._separator_in_group(box2, row_y)
        row_y += 1

        # Autostart switch
        autostart_sw = NSSwitch.alloc().initWithFrame_(NSMakeRect(0, 0, 38, 22))
        autostart_sw.setState_(1 if settings.autostart else 0)
        autostart_sw.setTarget_(self._action_delegate)
        autostart_sw.setAction_("onAutostartChanged:")
        self._autostart_switch = autostart_sw
        self._row_in_group(box2, "开机启动", autostart_sw, row_y)
        row_y += _ROW_H

        self._separator_in_group(box2, row_y)
        row_y += 1

        # Notification switch
        notif_sw = NSSwitch.alloc().initWithFrame_(NSMakeRect(0, 0, 38, 22))
        notif_sw.setState_(1 if settings.notification_on_complete else 0)
        notif_sw.setTarget_(self._action_delegate)
        notif_sw.setAction_("onNotificationChanged:")
        self._notification_switch = notif_sw
        self._row_in_group(box2, "完成通知", notif_sw, row_y)

        y += sec2_group_h + _SECTION_GAP

        # -- 数据 --
        self._section_header(view, "数据", y)
        y += sec1_label_h + 6

        box3 = self._group_box(view, y, sec3_group_h)

        # History limit field + unit label in a compound
        field_w, field_h = 60, 22
        unit_w, unit_h = 24, 18
        gap = 4
        compound2_w = field_w + gap + unit_w
        compound2_h = max(field_h, unit_h)

        compound2 = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, compound2_w, compound2_h)
        )

        hist_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, (compound2_h - field_h) / 2, field_w, field_h)
        )
        hist_field.setStringValue_(str(settings.history_max_entries))
        hist_field.setEditable_(True)
        hist_field.setAlignment_(1)  # center
        hist_field.setTarget_(self._action_delegate)
        hist_field.setAction_("onHistoryLimitChanged:")
        compound2.addSubview_(hist_field)
        self._history_limit_field = hist_field

        unit_lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(field_w + gap, (compound2_h - unit_h) / 2, unit_w, unit_h)
        )
        unit_lbl.setStringValue_("条")
        unit_lbl.setBezeled_(False)
        unit_lbl.setDrawsBackground_(False)
        unit_lbl.setEditable_(False)
        unit_lbl.setSelectable_(False)
        unit_lbl.setFont_(NSFont.systemFontOfSize_(13))
        compound2.addSubview_(unit_lbl)

        self._row_in_group(box3, "历史记录", compound2, _INNER_PAD)

        return view

    def _build_audio_view(self):
        settings = self._app._settings
        y = _PADDING

        sec_label_h = 16
        sec_gap = 6

        # 输入 section: 1 row
        input_group_h = _INNER_PAD + _ROW_H + _INNER_PAD
        # 反馈 section: 1 row with sublabel
        feedback_group_h = _INNER_PAD + _ROW_H_SUB + _INNER_PAD
        # 录音 section: 1 row with sublabel (slider + value label)
        recording_group_h = _INNER_PAD + _ROW_H_SUB + _INNER_PAD

        total_h = (
            _PADDING
            + sec_label_h + sec_gap
            + input_group_h + _SECTION_GAP
            + sec_label_h + sec_gap
            + feedback_group_h + _SECTION_GAP
            + sec_label_h + sec_gap
            + recording_group_h
            + _PADDING
        )

        view = _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, total_h)
        )

        # -- 输入 --
        self._section_header(view, "输入", y)
        y += sec_label_h + sec_gap

        box1 = self._group_box(view, y, input_group_h)

        mic_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(0, 0, 180, 26))
        mic_popup.setTarget_(self._action_delegate)
        mic_popup.setAction_("onMicChanged:")
        self._mic_popup = mic_popup
        self._populate_mic_list()
        self._row_in_group(box1, "麦克风", mic_popup, _INNER_PAD)

        y += input_group_h + _SECTION_GAP

        # -- 反馈 --
        self._section_header(view, "反馈", y)
        y += sec_label_h + sec_gap

        box2 = self._group_box(view, y, feedback_group_h)

        sound_sw = NSSwitch.alloc().initWithFrame_(NSMakeRect(0, 0, 38, 22))
        sound_sw.setState_(1 if settings.sound_feedback else 0)
        sound_sw.setTarget_(self._action_delegate)
        sound_sw.setAction_("onSoundFeedbackChanged:")
        self._sound_switch = sound_sw
        self._row_in_group(
            box2, "声音反馈", sound_sw,
            _INNER_PAD,
            sublabel="录音开始和转写完成时播放",
        )

        y += feedback_group_h + _SECTION_GAP

        # -- 录音 --
        self._section_header(view, "录音", y)
        y += sec_label_h + sec_gap

        box3 = self._group_box(view, y, recording_group_h)

        # Compound: slider + value label
        slider_w = 120
        val_label_w = 50
        gap = 8
        compound_w = slider_w + gap + val_label_w
        compound_h = _ROW_H_SUB

        compound = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, compound_w, compound_h)
        )

        slider = NSSlider.alloc().initWithFrame_(NSMakeRect(0, (compound_h - 22) / 2, slider_w, 22))
        slider.setMinValue_(10)
        slider.setMaxValue_(120)
        slider.setIntegerValue_(settings.max_recording_seconds)
        slider.setContinuous_(True)
        slider.setTarget_(self._action_delegate)
        slider.setAction_("onRecordingSliderChanged:")
        compound.addSubview_(slider)
        self._recording_slider = slider

        val_lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(slider_w + gap, (compound_h - 18) / 2, val_label_w, 18)
        )
        val_lbl.setStringValue_(f"{settings.max_recording_seconds} 秒")
        val_lbl.setBezeled_(False)
        val_lbl.setDrawsBackground_(False)
        val_lbl.setEditable_(False)
        val_lbl.setSelectable_(False)
        val_lbl.setFont_(NSFont.systemFontOfSize_(13))
        compound.addSubview_(val_lbl)
        self._recording_value_label = val_lbl

        self._row_in_group(
            box3, "最长录音", compound,
            _INNER_PAD,
            sublabel="超时自动停止转写",
        )

        return view

    def _populate_mic_list(self):
        """Fill mic popup from Recorder.list_input_devices(); always starts with 系统默认."""
        if self._mic_popup is None:
            return
        self._mic_popup.removeAllItems()
        self._mic_devices = [None]
        self._mic_popup.addItemWithTitle_("系统默认")
        try:
            from ohmyvoice.recorder import Recorder
            devices = Recorder.list_input_devices()
            for d in devices:
                name = d["name"]
                self._mic_popup.addItemWithTitle_(name)
                self._mic_devices.append(name)
        except Exception:
            pass
        # Select item matching current setting
        current = self._app._settings.input_device
        if current is None:
            self._mic_popup.selectItemAtIndex_(0)
        else:
            idx = self._mic_devices.index(current) if current in self._mic_devices else 0
            self._mic_popup.selectItemAtIndex_(idx)

    def _refresh_audio_devices(self):
        """Re-populate mic list (called when switching to audio tab)."""
        self._populate_mic_list()

    def _build_recognition_view(self):
        settings = self._app._settings
        y = _PADDING

        sec_label_h = 16
        sec_gap = 6
        text_view_h = 90
        hint_label_h = 18

        # PROMPT section: 1-row group box + text view + hint
        prompt_group_h = _INNER_PAD + _ROW_H + _INNER_PAD
        # 模型 section: 1-row group box + warning label
        quant_group_h = _INNER_PAD + _ROW_H + 22 + _INNER_PAD

        total_h = (
            _PADDING
            + sec_label_h + sec_gap
            + prompt_group_h + 8
            + text_view_h + 8
            + hint_label_h + _SECTION_GAP
            + sec_label_h + sec_gap
            + quant_group_h
            + _PADDING
        )

        view = _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, total_h)
        )

        # -- PROMPT 模板 --
        self._section_header(view, "PROMPT 模板", y)
        y += sec_label_h + sec_gap

        box1 = self._group_box(view, y, prompt_group_h)

        template_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(0, 0, 130, 26))
        for opt in _TEMPLATE_OPTIONS:
            template_popup.addItemWithTitle_(opt)
        current_tpl = settings.active_prompt_template
        sel_idx = _TEMPLATE_VALUES.index(current_tpl) if current_tpl in _TEMPLATE_VALUES else 0
        template_popup.selectItemAtIndex_(sel_idx)
        template_popup.setTarget_(self._action_delegate)
        template_popup.setAction_("onTemplateChanged:")
        self._template_popup = template_popup
        self._row_in_group(box1, "模板", template_popup, _INNER_PAD)

        y += prompt_group_h + 8

        # Text view (NSScrollView + NSTextView)
        is_custom = current_tpl == "custom"
        initial_text = settings.custom_prompt if is_custom else settings.get_active_prompt()
        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(_PADDING, y, _CONTENT_W, text_view_h)
        )
        tv = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _CONTENT_W, text_view_h)
        )
        tv.setFont_(NSFont.monospacedSystemFontOfSize_weight_(12, 0.0))
        tv.setString_(initial_text)
        tv.setEditable_(is_custom)
        tv.setBackgroundColor_(
            NSColor.textBackgroundColor() if is_custom else NSColor.controlBackgroundColor()
        )
        tv.setDelegate_(self._action_delegate)
        scroll.setDocumentView_(tv)
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(3)  # NSBezelBorder
        view.addSubview_(scroll)
        self._prompt_textview = tv

        y += text_view_h + 8

        # Hint label
        hint = NSTextField.alloc().initWithFrame_(
            NSMakeRect(_PADDING, y, _CONTENT_W, hint_label_h)
        )
        hint.setStringValue_('选择\u201c自定义\u201d后可编辑内容，预设模板仅供预览')
        hint.setBezeled_(False)
        hint.setDrawsBackground_(False)
        hint.setEditable_(False)
        hint.setSelectable_(False)
        hint.setFont_(NSFont.systemFontOfSize_(11))
        hint.setTextColor_(NSColor.secondaryLabelColor())
        view.addSubview_(hint)

        y += hint_label_h + _SECTION_GAP

        # -- 模型 --
        self._section_header(view, "模型", y)
        y += sec_label_h + sec_gap

        box2 = self._group_box(view, y, quant_group_h)

        quant_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(0, 0, 130, 26))
        for opt in _QUANT_OPTIONS:
            quant_popup.addItemWithTitle_(opt)
        current_quant = settings.model_quantization
        quant_idx = _QUANT_VALUES.index(current_quant) if current_quant in _QUANT_VALUES else 0
        quant_popup.selectItemAtIndex_(quant_idx)
        quant_popup.setTarget_(self._action_delegate)
        quant_popup.setAction_("onQuantChanged:")
        self._quant_popup = quant_popup
        self._row_in_group(box2, "精度", quant_popup, _INNER_PAD)

        # Warning label inside the group box
        warn = NSTextField.alloc().initWithFrame_(
            NSMakeRect(_INNER_PAD, _INNER_PAD + _ROW_H, _CONTENT_W - 2 * _INNER_PAD, 18)
        )
        warn.setStringValue_("⚠ 切换精度需要重新加载模型（约 5 秒）")
        warn.setBezeled_(False)
        warn.setDrawsBackground_(False)
        warn.setEditable_(False)
        warn.setSelectable_(False)
        warn.setFont_(NSFont.systemFontOfSize_(11))
        warn.setTextColor_(NSColor.systemOrangeColor())
        box2.addSubview_(warn)

        return view

    def _build_about_view(self):
        from ohmyvoice import __version__

        settings = self._app._settings
        engine = self._app._engine

        sec_label_h = 16
        sec_gap = 6

        # Heights
        icon_h = 48
        name_h = 24
        version_h = 18
        header_gap = 16  # gap below version before first section

        # 模型 section: 2 rows
        model_group_h = _INNER_PAD + _ROW_H + 1 + _ROW_H + _INNER_PAD

        # 链接 section: 2 rows
        links_group_h = _INNER_PAD + _ROW_H + 1 + _ROW_H + _INNER_PAD

        total_h = (
            _PADDING
            + icon_h + 8
            + name_h + 4
            + version_h + header_gap
            + sec_label_h + sec_gap
            + model_group_h + _SECTION_GAP
            + sec_label_h + sec_gap
            + links_group_h
            + _PADDING
        )

        view = _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _WINDOW_WIDTH, total_h)
        )

        y = _PADDING

        # ---- App icon ----
        icon_size = 48
        icon_img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "mic.fill", "OhMyVoice"
        )
        icon_view = NSImageView.alloc().initWithFrame_(
            NSMakeRect((_WINDOW_WIDTH - icon_size) // 2, y, icon_size, icon_size)
        )
        if icon_img:
            icon_view.setImage_(icon_img)
        icon_view.setContentTintColor_(NSColor.controlAccentColor())
        view.addSubview_(icon_view)
        y += icon_size + 8

        # ---- App name ----
        name_lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, y, _WINDOW_WIDTH, name_h)
        )
        name_lbl.setStringValue_("OhMyVoice")
        name_lbl.setBezeled_(False)
        name_lbl.setDrawsBackground_(False)
        name_lbl.setEditable_(False)
        name_lbl.setSelectable_(False)
        name_lbl.setAlignment_(1)  # NSTextAlignmentCenter
        name_lbl.setFont_(NSFont.boldSystemFontOfSize_(18))
        view.addSubview_(name_lbl)
        self._app_name_label = name_lbl
        y += name_h + 4

        # ---- Version ----
        version_lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, y, _WINDOW_WIDTH, version_h)
        )
        version_lbl.setStringValue_(f"版本 {__version__}")
        version_lbl.setBezeled_(False)
        version_lbl.setDrawsBackground_(False)
        version_lbl.setEditable_(False)
        version_lbl.setSelectable_(False)
        version_lbl.setAlignment_(1)  # NSTextAlignmentCenter
        version_lbl.setFont_(NSFont.systemFontOfSize_(12))
        version_lbl.setTextColor_(NSColor.secondaryLabelColor())
        view.addSubview_(version_lbl)
        y += version_h + header_gap

        # ---- 模型 section ----
        self._section_header(view, "模型", y)
        y += sec_label_h + sec_gap

        model_box = self._group_box(view, y, model_group_h)
        row_y = _INNER_PAD

        # Row 1: model name + load status
        model_name = settings.model_name
        model_quant = settings.model_quantization
        model_display = f"{model_name} ({model_quant})"

        is_loaded = getattr(engine, "is_loaded", False)
        status_lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 60, 18))
        status_lbl.setStringValue_("已加载" if is_loaded else "未加载")
        status_lbl.setBezeled_(False)
        status_lbl.setDrawsBackground_(False)
        status_lbl.setEditable_(False)
        status_lbl.setSelectable_(False)
        status_lbl.setAlignment_(2)  # NSTextAlignmentRight
        status_lbl.setFont_(NSFont.systemFontOfSize_(13))
        status_lbl.setTextColor_(
            NSColor.systemGreenColor() if is_loaded else NSColor.secondaryLabelColor()
        )
        self._row_in_group(model_box, model_display, status_lbl, row_y)
        row_y += _ROW_H

        self._separator_in_group(model_box, row_y)
        row_y += 1

        # Row 2: disk usage
        cache_path = _cache_dir_for_display(settings)
        size_str = _dir_size_str(cache_path)
        size_lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 80, 18))
        size_lbl.setStringValue_(size_str)
        size_lbl.setBezeled_(False)
        size_lbl.setDrawsBackground_(False)
        size_lbl.setEditable_(False)
        size_lbl.setSelectable_(False)
        size_lbl.setAlignment_(2)  # NSTextAlignmentRight
        size_lbl.setFont_(NSFont.systemFontOfSize_(13))
        size_lbl.setTextColor_(NSColor.secondaryLabelColor())
        self._row_in_group(model_box, "磁盘占用", size_lbl, row_y)

        y += model_group_h + _SECTION_GAP

        # ---- 链接 section ----
        self._section_header(view, "链接", y)
        y += sec_label_h + sec_gap

        links_box = self._group_box(view, y, links_group_h)
        row_y = _INNER_PAD

        # Row 1: GitHub
        gh_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 44, 22))
        gh_btn.setTitle_("打开")
        gh_btn.setBordered_(False)
        gh_btn.setContentTintColor_(NSColor.linkColor())
        gh_btn.setTarget_(self._action_delegate)
        gh_btn.setAction_("onOpenGitHub:")
        self._row_in_group(links_box, "GitHub 项目主页", gh_btn, row_y)
        row_y += _ROW_H

        self._separator_in_group(links_box, row_y)
        row_y += 1

        # Row 2: Feedback
        fb_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 44, 22))
        fb_btn.setTitle_("打开")
        fb_btn.setBordered_(False)
        fb_btn.setContentTintColor_(NSColor.linkColor())
        fb_btn.setTarget_(self._action_delegate)
        fb_btn.setAction_("onOpenFeedback:")
        self._row_in_group(links_box, "反馈与建议", fb_btn, row_y)

        return view

    # ---------------------------------------------------------------- hotkey capture

    def _start_hotkey_capture(self):
        """Enter hotkey capture mode."""
        from AppKit import NSEvent, NSEventMaskKeyDown

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


def _cache_dir_for_display(settings):
    from ohmyvoice.asr import _cache_dir_for
    bits = int(settings.model_quantization.replace("bit", ""))
    return _cache_dir_for(settings.model_name, bits)


def _dir_size_str(path):
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


def _make_point(x, y):
    """Return an NSPoint for setFrameOrigin_."""
    from Foundation import NSMakePoint
    return NSMakePoint(x, y)
