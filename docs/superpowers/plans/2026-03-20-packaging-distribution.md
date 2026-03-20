# OhMyVoice Packaging & Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package OhMyVoice as a signed, notarized `.app` bundle distributed via DMG.

**Architecture:** PyInstaller `--onedir --windowed` bundles the Python runtime + dependencies. Swift UI binary and static resources are post-build copied into the `.app` bundle. Inside-out codesign + notarization for Gatekeeper compliance.

**Tech Stack:** PyInstaller 6.x, codesign, notarytool, create-dmg, iconutil

**Spec:** `docs/superpowers/specs/2026-03-20-packaging-design.md`

---

## File Structure

**New files:**
- `src/ohmyvoice/paths.py` — resource path resolution (frozen vs dev)
- `ohmyvoice.spec` — PyInstaller spec
- `entitlements.plist` — codesign entitlements for Python binary
- `scripts/build_dmg.sh` — full build+sign+notarize+DMG script
- `scripts/generate_icons.py` — SVG → PNG icon generation script
- `resources/AppIcon.icns` — app icon (generated)
- `resources/icons/*.png` — new menu bar icons (generated, replace existing)

**Modified files:**
- `src/ohmyvoice/app.py` — use `paths.get_resources_dir()` for icons
- `src/ohmyvoice/audio_feedback.py` — use `paths.get_resources_dir()` for sounds
- `src/ohmyvoice/autostart.py` — frozen-aware plist generation
- `src/ohmyvoice/ui_bridge.py` — reorder `_find_binary` search
- `Makefile` — add dist/sign/notarize/dmg targets
- `pyproject.toml` — add `dist` optional dependency group

**Test files:**
- `tests/test_paths.py` — new, tests `get_resources_dir()` in both modes
- `tests/test_autostart.py` — update for new `generate_plist()` signature
- `tests/test_ui_bridge.py` — add test for frozen-first `_find_binary` order

---

### Task 1: Resource Path Module

**Files:**
- Create: `src/ohmyvoice/paths.py`
- Create: `tests/test_paths.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_paths.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ohmyvoice.paths'`

- [ ] **Step 3: Write implementation**

```python
# src/ohmyvoice/paths.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_paths.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/paths.py tests/test_paths.py
git commit -m "feat: add paths module for frozen/dev resource resolution"
```

---

### Task 2: Wire Resource Paths into App and Audio Feedback

**Files:**
- Modify: `src/ohmyvoice/app.py:32`
- Modify: `src/ohmyvoice/audio_feedback.py:1-5`

- [ ] **Step 1: Update `app.py` icon path**

In `src/ohmyvoice/app.py`, replace line 32:

```python
# Old:
_ICONS = Path(__file__).parent.parent.parent / "resources" / "icons"

# New:
from ohmyvoice.paths import get_resources_dir
_ICONS = get_resources_dir() / "icons"
```

Also remove the `from pathlib import Path` import if it's only used for `_ICONS` (check first — `Path` may be used elsewhere in the file). In this case `Path` is NOT used elsewhere in `app.py`, so remove it.

- [ ] **Step 2: Update `audio_feedback.py` sounds path**

In `src/ohmyvoice/audio_feedback.py`, replace lines 1-5:

```python
# Old:
from pathlib import Path
from AppKit import NSSound

_RESOURCES = Path(__file__).parent.parent.parent / "resources" / "sounds"

# New:
from AppKit import NSSound
from ohmyvoice.paths import get_resources_dir

_RESOURCES = get_resources_dir() / "sounds"
```

Also remove the `from pathlib import Path` import. `Path` is used in `_SYSTEM_SOUNDS` on line 5 — so keep it? Check: `_SYSTEM_SOUNDS = Path("/System/Library/Sounds")`. Yes, `Path` is still needed. **Keep the import.**

Corrected change for `audio_feedback.py`:

```python
# Old:
_RESOURCES = Path(__file__).parent.parent.parent / "resources" / "sounds"

# New:
from ohmyvoice.paths import get_resources_dir
_RESOURCES = get_resources_dir() / "sounds"
```

- [ ] **Step 3: Run existing tests to verify nothing broke**

Run: `python -m pytest tests/ -v --ignore=tests/test_asr.py --ignore=tests/test_recorder.py`
Expected: All existing tests PASS (asr/recorder tests may need hardware, skip them)

- [ ] **Step 4: Commit**

```bash
git add src/ohmyvoice/app.py src/ohmyvoice/audio_feedback.py
git commit -m "refactor: use paths module for resource resolution in app and audio_feedback"
```

---

### Task 3: Autostart Frozen-Aware Plist

**Files:**
- Modify: `src/ohmyvoice/autostart.py`
- Modify: `tests/test_autostart.py`

- [ ] **Step 1: Write failing tests for new behavior**

Add to `tests/test_autostart.py`:

```python
import sys
from unittest.mock import patch


def test_generate_plist_dev_mode():
    """Dev mode: plist uses python -m ohmyvoice.app."""
    from ohmyvoice.autostart import generate_plist
    xml = generate_plist()
    assert "com.ohmyvoice.app" in xml
    assert sys.executable in xml
    assert "-m" in xml
    assert "ohmyvoice.app" in xml


def test_generate_plist_frozen_mode(tmp_path):
    """Frozen mode: plist uses open <app_path>."""
    fake_exe = str(tmp_path / "OhMyVoice.app" / "Contents" / "MacOS" / "ohmyvoice")
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", fake_exe):
        from importlib import reload
        import ohmyvoice.autostart
        reload(ohmyvoice.autostart)
        xml = ohmyvoice.autostart.generate_plist()

    assert "<string>open</string>" in xml
    assert str(tmp_path / "OhMyVoice.app") in xml
    assert "-m" not in xml
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `python -m pytest tests/test_autostart.py -v`
Expected: new tests FAIL — `generate_plist()` still takes positional args

- [ ] **Step 3: Rewrite `autostart.py`**

Replace `generate_plist` function in `src/ohmyvoice/autostart.py`:

```python
import sys
from pathlib import Path

_LABEL = "com.ohmyvoice.app"


def get_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def generate_plist() -> str:
    if getattr(sys, "frozen", False):
        app_path = str(Path(sys.executable).parent.parent.parent)
        program_args = f"""
        <string>open</string>
        <string>{app_path}</string>"""
    else:
        program_args = f"""
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>ohmyvoice.app</string>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>{program_args}
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
```

- [ ] **Step 4: Update old test to match new signature**

In `tests/test_autostart.py`, update `test_generate_plist`:

```python
# Old:
def test_generate_plist():
    xml = generate_plist(python_path="/usr/bin/python3", module="ohmyvoice.app")
    assert "com.ohmyvoice.app" in xml
    assert "/usr/bin/python3" in xml

# Remove this test — replaced by test_generate_plist_dev_mode
```

- [ ] **Step 5: Run all autostart tests**

Run: `python -m pytest tests/test_autostart.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/ohmyvoice/autostart.py tests/test_autostart.py
git commit -m "feat: frozen-aware autostart plist generation"
```

---

### Task 4: Reorder `_find_binary` in UIBridge

**Files:**
- Modify: `src/ohmyvoice/ui_bridge.py:52-73`
- Modify: `tests/test_ui_bridge.py`

- [ ] **Step 1: Write failing test for frozen-first search order**

Add to `tests/test_ui_bridge.py`:

```python
def test_find_binary_frozen_before_dev(tmp_path, monkeypatch):
    """In frozen mode, check bundle path before dev path."""
    import sys
    import ohmyvoice.ui_bridge as ub

    # Create a "dev" binary at the real project's expected dev path
    # We monkeypatch __file__ so the dev-path lookup resolves to our tmp_path
    fake_project = tmp_path / "project"
    fake_src = fake_project / "src" / "ohmyvoice"
    fake_src.mkdir(parents=True)
    dev_binary = fake_project / "ui" / ".build" / "release" / "ohmyvoice-ui"
    dev_binary.parent.mkdir(parents=True)
    dev_binary.touch()

    # Also create a "frozen" binary
    frozen_binary = tmp_path / "bundle" / "Contents" / "MacOS" / "ohmyvoice-ui"
    frozen_binary.parent.mkdir(parents=True)
    frozen_binary.touch()
    fake_exe = str(frozen_binary.parent / "ohmyvoice")

    app = MagicMock()
    bridge = UIBridge(app)

    # Monkeypatch __file__ so dev path resolves to our tmp tree
    monkeypatch.setattr(ub, "__file__", str(fake_src / "ui_bridge.py"))

    with monkeypatch.context() as m:
        m.setattr(sys, "frozen", True, raising=False)
        m.setattr(sys, "executable", fake_exe)
        result = bridge._find_binary()

    # Must find the frozen binary, not the dev one
    assert result == frozen_binary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui_bridge.py::test_find_binary_frozen_before_dev -v`
Expected: FAIL — current code checks dev path first, finds `dev_binary` since we monkeypatched `__file__` to point at the tmp project tree

- [ ] **Step 3: Reorder `_find_binary` in `ui_bridge.py`**

**First**, add `import sys` to the top-level imports (currently `sys` is only imported inline at line 67 inside the old `if getattr(sys, "frozen"):` block). Add it after the existing imports at the top of the file:

```python
# At top of ui_bridge.py, after existing imports:
import sys
```

**Then**, replace the `_find_binary` method (lines 52-73):

```python
    def _find_binary(self) -> Path | None:
        # 1. Environment override
        env_path = os.environ.get("OHMYVOICE_UI_PATH")
        if env_path:
            p = Path(env_path)
            if p.exists():
                return p

        # 2. App bundle (frozen): Contents/MacOS/ohmyvoice-ui
        if getattr(sys, "frozen", False):
            bundle_path = Path(sys.executable).parent / "ohmyvoice-ui"
            if bundle_path.exists():
                return bundle_path

        # 3. Development: <project>/ui/.build/release/ohmyvoice-ui
        project_root = Path(__file__).parent.parent.parent
        dev_path = project_root / "ui" / ".build" / "release" / "ohmyvoice-ui"
        if dev_path.exists():
            return dev_path

        return None
```

**Also** remove the old inline `import sys` that was inside the previous `if getattr(sys, "frozen")` block (line 67).

- [ ] **Step 4: Run all ui_bridge tests**

Run: `python -m pytest tests/test_ui_bridge.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ohmyvoice/ui_bridge.py tests/test_ui_bridge.py
git commit -m "fix: check frozen bundle path before dev path in _find_binary"
```

---

### Task 5: Menu Bar Icons

**Files:**
- Create: `scripts/generate_icons.py`
- Modify: `resources/icons/mic_idle.png` (replace)
- Modify: `resources/icons/mic_recording.png` (replace)
- Modify: `resources/icons/mic_processing.png` (replace)
- Modify: `resources/icons/mic_done.png` (replace)
- Create: `resources/icons/mic_idle@2x.png`
- Create: `resources/icons/mic_recording@2x.png`
- Create: `resources/icons/mic_processing@2x.png`
- Create: `resources/icons/mic_done@2x.png`

- [ ] **Step 1: Create icon generation script**

Create `scripts/generate_icons.py` that uses Python's `cairosvg` or a pure-Python SVG-to-PNG approach. The script should:

1. Define an SVG template for a clean microphone outline (18×18pt)
2. Generate 4 states:
   - `mic_idle` — monochrome black (template image, macOS inverts for dark mode)
   - `mic_recording` — red (#FF3B30) with subtle pulse indicator
   - `mic_processing` — purple (#AF52DE) with processing dots
   - `mic_done` — green (#34C759) with checkmark indicator
3. Export each at @1x (18px) and @2x (36px)
4. Save to `resources/icons/`

The icons should be clean, minimal, recognizable at small sizes. Use a rounded-rect microphone shape with a small stand/base.

Dependencies: `pip install cairosvg pillow` (one-time for generation, not runtime)

- [ ] **Step 2: Run the generation script**

Run: `python scripts/generate_icons.py`
Verify: 8 PNG files in `resources/icons/` at correct sizes

- [ ] **Step 3: Visual verification**

Open each icon and verify:
- @1x files are 18×18px
- @2x files are 36×36px
- idle is pure monochrome (for template mode)
- Colors are correct for recording/processing/done
- Microphone shape is clear at small size

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_icons.py resources/icons/
git commit -m "feat: redesign menu bar icons — microphone outline with state colors"
```

---

### Task 6: App Icon

**Files:**
- Create: `scripts/generate_app_icon.py`
- Create: `resources/AppIcon.iconset/` (intermediate, deleted after)
- Create: `resources/AppIcon.icns`

- [ ] **Step 1: Create app icon generation script**

Create `scripts/generate_app_icon.py` that:

1. Generates a 1024×1024 app icon as SVG/PNG:
   - Clean, fresh design with a microphone as the central element
   - Rounded-rect background (macOS standard squircle)
   - Light gradient background, microphone in the foreground
   - Distinguishable from standard Apple mic icon
2. Creates an `.iconset` directory with all required sizes:
   - `icon_16x16.png`, `icon_16x16@2x.png`
   - `icon_32x32.png`, `icon_32x32@2x.png`
   - `icon_128x128.png`, `icon_128x128@2x.png`
   - `icon_256x256.png`, `icon_256x256@2x.png`
   - `icon_512x512.png`, `icon_512x512@2x.png`
3. Runs `iconutil -c icns resources/AppIcon.iconset -o resources/AppIcon.icns`
4. Cleans up the `.iconset` directory

- [ ] **Step 2: Run the generation script**

Run: `python scripts/generate_app_icon.py`
Verify: `resources/AppIcon.icns` exists

- [ ] **Step 3: Verify icon**

Run: `file resources/AppIcon.icns`
Expected: `resources/AppIcon.icns: Mac OS X icon, ...`

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_app_icon.py resources/AppIcon.icns
git commit -m "feat: generate app icon with microphone design"
```

---

### Task 7: Entitlements File

**Files:**
- Create: `entitlements.plist`

- [ ] **Step 1: Create entitlements.plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.device.audio-input</key>
    <true/>
    <key>com.apple.security.automation.apple-events</key>
    <true/>
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 2: Verify plist is valid**

Run: `plutil -lint entitlements.plist`
Expected: `entitlements.plist: OK`

- [ ] **Step 3: Commit**

```bash
git add entitlements.plist
git commit -m "feat: add entitlements for codesign (mic, JIT, library validation)"
```

---

### Task 8: PyInstaller Spec File

**Files:**
- Create: `ohmyvoice.spec`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dist dependency group to pyproject.toml**

Add to `pyproject.toml` under `[project.optional-dependencies]`:

```toml
dist = [
    "pyinstaller>=6.0",
]
```

- [ ] **Step 2: Install dist dependencies**

Run: `pip install -e ".[dist]"`

- [ ] **Step 3: Create `ohmyvoice.spec`**

```python
# ohmyvoice.spec — PyInstaller configuration for OhMyVoice
# Usage: pyinstaller ohmyvoice.spec --noconfirm

import re
from PyInstaller.utils.hooks import collect_submodules

# Read version from source to keep spec and __init__.py in sync
_version_match = re.search(
    r'__version__ = "(.+?)"',
    open('src/ohmyvoice/__init__.py').read(),
)
VERSION = _version_match.group(1) if _version_match else '0.0.0'

# PyObjC uses runtime __import__ and objc.loadBundle — must collect explicitly
hiddenimports = [
    'mlx', 'mlx.core', 'mlx.nn',
    'mlx_qwen3_asr',
    'sounddevice', '_sounddevice_data',
    'rumps',
    'numpy',
    'huggingface_hub',
    'AppKit', 'Foundation', 'Quartz', 'objc',
]
hiddenimports += collect_submodules('AppKit')
hiddenimports += collect_submodules('Quartz')

a = Analysis(
    ['src/ohmyvoice/__main__.py'],
    pathex=['src'],
    hiddenimports=hiddenimports,
    excludes=['pytest', '_pytest', 'coverage', 'pip', 'setuptools'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ohmyvoice',
    debug=False,
    strip=False,  # don't strip — breaks codesign
    upx=False,    # don't compress — breaks codesign
    console=False,
    target_arch='arm64',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='ohmyvoice',
)

app = BUNDLE(
    coll,
    name='OhMyVoice.app',
    icon='resources/AppIcon.icns',
    bundle_identifier='com.ohmyvoice.app',
    info_plist={
        'CFBundleName': 'OhMyVoice',
        'CFBundleDisplayName': 'OhMyVoice',
        'CFBundleShortVersionString': VERSION,
        'LSUIElement': True,
        'NSMicrophoneUsageDescription': '语音转文字需要访问麦克风',
        'NSHighResolutionCapable': True,
    },
)
```

- [ ] **Step 4: Test that PyInstaller can parse the spec**

Run: `python -c "exec(open('ohmyvoice.spec').read())"`
Expected: May fail (Analysis needs PyInstaller internals), but should not have syntax errors. Better test:

Run: `pyinstaller ohmyvoice.spec --noconfirm 2>&1 | head -20`
Expected: Should start processing (may take a few minutes). If it errors on imports, that's expected for a first pass — note the errors for debugging.

- [ ] **Step 5: Commit**

```bash
git add ohmyvoice.spec pyproject.toml
git commit -m "feat: PyInstaller spec and dist dependency group"
```

---

### Task 9: Build Script

**Files:**
- Create: `scripts/build_dmg.sh`

- [ ] **Step 1: Create the build script**

Write `scripts/build_dmg.sh` with the full content from spec Section 6. Copy it exactly — it handles:
1. Swift build
2. PyInstaller
3. Post-build copy (resources + Swift binary)
4. Pre-flight check (@2x icons)
5. Inside-out codesign (Mach-O detection via `file`)
6. Notarize (zip → submit → wait → rm zip)
7. Staple
8. Create DMG (rm stale first)
9. Sign + notarize DMG

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/build_dmg.sh`

- [ ] **Step 3: Verify script syntax**

Run: `bash -n scripts/build_dmg.sh`
Expected: No output (syntax OK)

- [ ] **Step 4: Commit**

```bash
git add scripts/build_dmg.sh
git commit -m "feat: build_dmg.sh — full build, sign, notarize, DMG pipeline"
```

---

### Task 10: Makefile Extension

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add new targets to Makefile**

Add the following after existing targets in `Makefile`. Content from spec Section 8:

```makefile
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/ohmyvoice/__init__.py)

dist: build-swift
	pyinstaller ohmyvoice.spec --noconfirm
	mkdir -p dist/OhMyVoice.app/Contents/Resources
	cp -R resources/icons dist/OhMyVoice.app/Contents/Resources/icons
	cp -R resources/sounds dist/OhMyVoice.app/Contents/Resources/sounds 2>/dev/null || true
	cp resources/AppIcon.icns dist/OhMyVoice.app/Contents/Resources/AppIcon.icns 2>/dev/null || true
	cp ui/.build/release/ohmyvoice-ui dist/OhMyVoice.app/Contents/MacOS/

app: dist

sign:
	@# inside-out signing: _internal/ Mach-O → Swift binary → Python binary → outer bundle
	find dist/OhMyVoice.app/Contents/MacOS/_internal -type f \( -name '*.dylib' -o -name '*.so' -o -perm +111 \) -exec sh -c \
		'file "$$1" | grep -q "Mach-O" && codesign --force --options runtime --sign "$(DEVELOPER_ID_APPLICATION)" "$$1"' _ {} \;
	codesign --force --options runtime --sign "$(DEVELOPER_ID_APPLICATION)" \
		dist/OhMyVoice.app/Contents/MacOS/ohmyvoice-ui
	codesign --force --options runtime --sign "$(DEVELOPER_ID_APPLICATION)" \
		--entitlements entitlements.plist dist/OhMyVoice.app/Contents/MacOS/ohmyvoice
	codesign --force --options runtime --sign "$(DEVELOPER_ID_APPLICATION)" \
		--entitlements entitlements.plist dist/OhMyVoice.app

notarize:
	ditto -c -k --keepParent dist/OhMyVoice.app dist/OhMyVoice.zip
	xcrun notarytool submit dist/OhMyVoice.zip \
		--apple-id "$(APPLE_ID)" --team-id "$(APPLE_TEAM_ID)" \
		--password "$(APP_PASSWORD)" --wait
	rm dist/OhMyVoice.zip
	xcrun stapler staple dist/OhMyVoice.app

dmg: dist sign notarize
	rm -f dist/OhMyVoice-$(VERSION)-arm64.dmg
	create-dmg --volname OhMyVoice --window-size 600 400 \
		--icon-size 128 --icon OhMyVoice.app 150 200 \
		--app-drop-link 450 200 \
		dist/OhMyVoice-$(VERSION)-arm64.dmg dist/OhMyVoice.app
	codesign --sign "$(DEVELOPER_ID_APPLICATION)" dist/OhMyVoice-$(VERSION)-arm64.dmg
	xcrun notarytool submit dist/OhMyVoice-$(VERSION)-arm64.dmg \
		--apple-id "$(APPLE_ID)" --team-id "$(APPLE_TEAM_ID)" \
		--password "$(APP_PASSWORD)" --wait
	xcrun stapler staple dist/OhMyVoice-$(VERSION)-arm64.dmg
```

Also update the `.PHONY` line at the top to include the new targets:

```makefile
.PHONY: build build-swift build-python test test-swift test-python clean run dist app sign notarize dmg
```

- [ ] **Step 2: Verify Makefile syntax**

Run: `make -n dist 2>&1 | head -5`
Expected: Shows the commands that would run (dry run)

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat: Makefile targets for dist, sign, notarize, dmg"
```

---

### Task 11: Smoke Test — `make dist` (unsigned)

This task verifies the entire PyInstaller pipeline produces a working `.app` bundle. No signing/notarization (those require developer credentials at runtime).

**Files:** None (validation only)

- [ ] **Step 1: Run `make dist`**

Run: `make dist`
Expected: Builds Swift UI, runs PyInstaller, copies resources and Swift binary. Should produce `dist/OhMyVoice.app/`.

Watch for:
- PyInstaller hidden import errors → fix in `ohmyvoice.spec`
- Missing Metal/mlx files → may need `datas` for `.metallib` files
- PyObjC import failures → may need more `collect_submodules`

- [ ] **Step 2: Verify bundle structure**

Run: `ls -la dist/OhMyVoice.app/Contents/MacOS/`
Expected: `ohmyvoice`, `ohmyvoice-ui`, `_internal/` directory

Run: `ls dist/OhMyVoice.app/Contents/Resources/icons/`
Expected: All 8 icon PNGs

Run: `file dist/OhMyVoice.app/Contents/MacOS/ohmyvoice`
Expected: `Mach-O 64-bit executable arm64`

- [ ] **Step 3: Test launch**

Run: `dist/OhMyVoice.app/Contents/MacOS/ohmyvoice`
Expected: Menu bar icon appears (may need Accessibility permission grant). Ctrl-C to stop.

If it crashes, check the error. Common issues:
- `ModuleNotFoundError` → add to hiddenimports in spec
- `Library not loaded` → add binary to spec or post-build copy
- Icon not found → verify resource path resolution

- [ ] **Step 4: Fix any issues found and re-run**

Iterate on `ohmyvoice.spec` until `make dist` produces a working app.

- [ ] **Step 5: Commit any spec fixes**

```bash
git add ohmyvoice.spec
git commit -m "fix: PyInstaller spec adjustments from smoke test"
```

---

### Task 12: Add `dist/`, `build/` to `.gitignore`

**Files:**
- Modify or create: `.gitignore`

- [ ] **Step 1: Add build artifacts to `.gitignore`**

Append to `.gitignore`:

```
# PyInstaller
dist/
build/
*.spec.bak
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore PyInstaller build artifacts"
```
