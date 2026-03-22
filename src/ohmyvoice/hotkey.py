import threading
from typing import Callable
import Quartz

_MODIFIER_FLAGS = {
    "command": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "control": Quartz.kCGEventFlagMaskControl,
}

_KEY_CODES = {
    "space": 49, "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3,
    "g": 5, "h": 4, "i": 34, "j": 38, "k": 40, "l": 37, "m": 46,
    "n": 45, "o": 31, "p": 35, "q": 12, "r": 15, "s": 1, "t": 17,
    "u": 32, "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
    "return": 36, "tab": 48, "escape": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
}

class HotkeyManager:
    def __init__(self, modifiers: list[str], key: str, on_press: Callable, on_release: Callable):
        self._modifiers = modifiers
        self._key = key
        self._on_press = on_press
        self._on_release = on_release
        self._tap = None
        self._thread = None
        self._running = False
        self._key_held = False

    def start(self) -> bool:
        mask = (
            1 << Quartz.kCGEventKeyDown
            | 1 << Quartz.kCGEventKeyUp
            | 1 << Quartz.kCGEventFlagsChanged
        )
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._callback,
            None,
        )
        if self._tap is None:
            return False
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

    def pause(self):
        """Temporarily disable the event tap (e.g., during hotkey capture)."""
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, False)

    def resume(self):
        """Re-enable the event tap after pause."""
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, True)

    def update_hotkey(self, modifiers: list[str], key: str):
        self._modifiers = modifiers
        self._key = key
        self._key_held = False

    def _callback(self, proxy, event_type, event, refcon):
        if event_type in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            if self._tap:
                Quartz.CGEventTapEnable(self._tap, True)
            return event

        key_code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        target_code = _KEY_CODES.get(self._key)
        if target_code is None:
            return event
        required_flags = 0
        for mod in self._modifiers:
            required_flags |= _MODIFIER_FLAGS.get(mod, 0)
        modifiers_match = (flags & required_flags) == required_flags

        if event_type == Quartz.kCGEventKeyDown and key_code == target_code and modifiers_match:
            if not self._key_held:
                self._key_held = True
                self._on_press()
            return None
        if event_type == Quartz.kCGEventKeyUp and key_code == target_code and self._key_held:
            self._key_held = False
            self._on_release()
            return None
        return event
