"""Resource path resolution for frozen (PyInstaller) and development modes."""

import sys
from pathlib import Path


def get_resources_dir() -> Path:
    """Return the resources directory.

    Frozen (PyInstaller onedir bundle): Contents/MacOS/ohmyvoice → ../Resources
    Development: src/ohmyvoice/paths.py → ../../../resources
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.parent / "Resources"
    return Path(__file__).parent.parent.parent / "resources"
