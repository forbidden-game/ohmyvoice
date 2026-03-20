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
    strip=False,
    upx=False,
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
