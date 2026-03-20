import json
import tempfile
from pathlib import Path

from ohmyvoice.settings import Settings


def test_reload_picks_up_file_changes():
    with tempfile.TemporaryDirectory() as d:
        s = Settings(config_dir=Path(d))
        assert s.language == "auto"

        # Simulate Swift writing to settings.json
        data = json.loads(s.path.read_text())
        data["language"] = "zh"
        s.path.write_text(json.dumps(data))

        s.reload()
        assert s.language == "zh"


def test_path_property():
    with tempfile.TemporaryDirectory() as d:
        s = Settings(config_dir=Path(d))
        assert s.path == Path(d) / "settings.json"
