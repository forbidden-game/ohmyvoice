from pathlib import Path
from ohmyvoice.autostart import get_plist_path, generate_plist

def test_plist_path():
    path = get_plist_path()
    assert "LaunchAgents" in str(path)
    assert "ohmyvoice" in str(path).lower()

def test_generate_plist():
    xml = generate_plist(python_path="/usr/bin/python3", module="ohmyvoice.app")
    assert "com.ohmyvoice.app" in xml
    assert "/usr/bin/python3" in xml
