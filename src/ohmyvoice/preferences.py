"""macOS native preferences window with 4 toolbar tabs."""

import objc
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSBox,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSObject,
    NSPopUpButton,
    NSSwitch,
    NSTextField,
    NSToolbar,
    NSToolbarItem,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect, NSMakeSize

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
        # Placeholder — actual capture logic comes in Task 6
        pass


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


def _make_point(x, y):
    """Return an NSPoint for setFrameOrigin_."""
    from Foundation import NSMakePoint
    return NSMakePoint(x, y)
