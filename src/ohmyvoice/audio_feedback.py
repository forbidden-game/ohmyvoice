from pathlib import Path
from AppKit import NSSound

from ohmyvoice.paths import get_resources_dir
_RESOURCES = get_resources_dir() / "sounds"
_SYSTEM_SOUNDS = Path("/System/Library/Sounds")


def play_start():
    _play("start.aiff", fallback="Tink.aiff")


def play_done():
    _play("done.aiff", fallback="Pop.aiff")


def _play(name: str, fallback: str = ""):
    path = _RESOURCES / name
    if not path.exists():
        path = _SYSTEM_SOUNDS / fallback
    if path.exists():
        sound = NSSound.alloc().initWithContentsOfFile_byReference_(str(path), True)
        if sound:
            sound.play()
