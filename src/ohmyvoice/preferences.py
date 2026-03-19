"""macOS native preferences window with 4 toolbar tabs."""

import objc
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSImage,
    NSObject,
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
