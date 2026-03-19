import sys
from pathlib import Path

_LABEL = "com.ohmyvoice.app"

def get_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"

def generate_plist(python_path: str | None = None, module: str = "ohmyvoice.app") -> str:
    if python_path is None:
        python_path = sys.executable
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>{module}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""

def enable():
    path = get_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_plist())

def disable():
    path = get_plist_path()
    if path.exists():
        path.unlink()

def is_enabled() -> bool:
    return get_plist_path().exists()
