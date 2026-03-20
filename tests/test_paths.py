import sys
from pathlib import Path
from unittest.mock import patch


def test_get_resources_dir_dev_mode():
    """In dev mode (not frozen), returns <project>/resources."""
    from ohmyvoice.paths import get_resources_dir

    result = get_resources_dir()
    # paths.py is at src/ohmyvoice/paths.py → parent.parent.parent = project root
    assert result.name == "resources"
    assert (result.parent / "src" / "ohmyvoice").is_dir()


def test_get_resources_dir_frozen_mode(tmp_path):
    """In frozen mode, returns Contents/Resources relative to executable."""
    # Simulate: Contents/MacOS/ohmyvoice (executable)
    macos_dir = tmp_path / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True)
    resources_dir = tmp_path / "Contents" / "Resources"
    resources_dir.mkdir(parents=True)
    fake_exe = str(macos_dir / "ohmyvoice")

    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", fake_exe):
        from importlib import reload
        import ohmyvoice.paths
        reload(ohmyvoice.paths)
        result = ohmyvoice.paths.get_resources_dir()

    assert result == resources_dir
