# OhMyVoice 打包分发设计

## 概述

将 OhMyVoice（Python rumps 菜单栏 + SwiftUI 子进程）打包为可分发的 macOS `.app` bundle，通过 DMG 分发，支持代码签名和公证。后续可加 Homebrew cask。

## 约束

- Apple Silicon only（MLX 依赖）
- macOS 14+ （SwiftUI target）
- 用户需要 Apple Developer ID 证书用于签名和公证
- 模型不内置，首次启动从 HuggingFace 下载（~600MB）

## 1. 打包工具选择

**PyInstaller**，`--onedir --windowed` 模式。

理由：
- 代码已预留 `sys.frozen` 检测（`ui_bridge.py:67-71`）
- hook 机制可处理 mlx 等原生扩展的 Metal shader
- 签名公证流程有成熟实践
- 不用 `--onefile`，避免 200MB+ 包每次启动解压的延迟

## 2. Bundle 结构

```
OhMyVoice.app/
└── Contents/
    ├── Info.plist
    ├── MacOS/
    │   ├── ohmyvoice           # PyInstaller 主可执行文件
    │   ├── ohmyvoice-ui        # Swift 编译产物（post-build copy）
    │   └── _internal/          # PyInstaller 6.x 放 Python 运行时和所有 .so/.dylib
    │       ├── lib-dynload/
    │       ├── mlx/
    │       ├── numpy/
    │       └── ...
    └── Resources/              # post-build copy 的静态资源
        ├── icons/
        │   ├── mic_idle.png
        │   ├── mic_idle@2x.png
        │   ├── mic_recording.png
        │   ├── mic_recording@2x.png
        │   ├── mic_processing.png
        │   ├── mic_processing@2x.png
        │   ├── mic_done.png
        │   └── mic_done@2x.png
        ├── sounds/
        └── AppIcon.icns
```

注意：PyInstaller 6.x `--onedir --windowed` 不生成 `Contents/Frameworks/`，所有 `.so`/`.dylib` 在 `Contents/MacOS/_internal/` 内。签名必须覆盖这个目录。

## 3. PyInstaller .spec 文件

文件：`ohmyvoice.spec`（项目根目录）

关键配置：
- **入口**：`src/ohmyvoice/__main__.py`
- **hiddenimports**：`mlx`、`mlx.core`、`mlx.nn`、`mlx_qwen3_asr`、`sounddevice`、`_sounddevice_data`、`rumps`、`numpy`、`huggingface_hub`、`AppKit`、`Quartz`、`Foundation`、`objc`（PyObjC 用 runtime `__import__` 和 `objc.loadBundle`，PyInstaller 无法自动追踪）
- **collect_submodules**：`AppKit`、`Quartz`（确保 PyObjC bridge 的子模块完整收集）
- **excludes**：`pytest`、`_pytest`、`coverage`、`pip`、`setuptools`
- **BUNDLE** 参数：`name='OhMyVoice'`、`bundle_identifier='com.ohmyvoice.app'`、`icon='resources/AppIcon.icns'`
- **Info.plist 覆盖**：
  - `NSMicrophoneUsageDescription`：语音转文字需要访问麦克风
  - `LSUIElement`：`True`（无 Dock 图标，纯菜单栏应用）

**资源和二进制文件不通过 spec 的 datas/binaries 嵌入**。PyInstaller 的 `datas` 会放到 `_internal/` 目录而非 `Contents/Resources/`。改用构建脚本的 post-build copy：
- `resources/icons/` → `Contents/Resources/icons/`
- `resources/sounds/` → `Contents/Resources/sounds/`（当前为空，系统音效兜底）
- `resources/AppIcon.icns` → `Contents/Resources/AppIcon.icns`
- `ui/.build/release/ohmyvoice-ui` → `Contents/MacOS/ohmyvoice-ui`

## 4. 代码适配

### 4a. 资源路径（新增 `src/ohmyvoice/paths.py`）

```python
import sys
from pathlib import Path

def get_resources_dir() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller onedir bundle: Contents/MacOS/ohmyvoice
        # Resources 在 Contents/Resources/
        return Path(sys.executable).parent.parent / "Resources"
    # 开发环境：src/ohmyvoice/../../resources
    return Path(__file__).parent.parent.parent / "resources"
```

**修改文件**：
- `app.py:32`：`_ICONS = get_resources_dir() / "icons"`
- `audio_feedback.py:4`：`_RESOURCES = get_resources_dir() / "sounds"`

### 4b. 自启动（修改 `autostart.py`）

`generate_plist()` 需要区分两种运行模式：

```python
def generate_plist() -> str:
    if getattr(sys, "frozen", False):
        # .app bundle: Contents/MacOS/ohmyvoice → 向上三级得到 .app 路径
        app_path = str(Path(sys.executable).parent.parent.parent)
        program_args = f"""
        <string>open</string>
        <string>{app_path}</string>"""
    else:
        # 开发环境：python -m ohmyvoice.app
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
    <string>com.ohmyvoice.app</string>
    <key>ProgramArguments</key>
    <array>{program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""
```

`enable()` 和 `disable()` 保持不变，调用 `generate_plist()` 时不再传参。原来的 `python_path` 和 `module` 参数移除。

### 4c. ui_bridge.py `_find_binary` 搜索顺序调整

现有代码先查开发路径再查 frozen 路径。在 frozen 模式下 `Path(__file__)` 指向 `_internal/` 目录，开发路径不会命中所以碰巧能工作——但如果 .app 恰好放在项目目录内（比如 dist/ 下），开发路径可能意外匹配。

修改：把 `sys.frozen` 检测提到最前面，env override 之后、dev path 之前：

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

## 5. 图标设计

### 菜单栏图标
- 从纯色圆点升级为精致的麦克风轮廓图形
- 尺寸：18×18pt，提供 @1x（18px）和 @2x（36px）
- idle 状态：template image（跟随系统深浅色自动切换）
- recording：红色麦克风 + 脉冲指示
- processing：紫色麦克风 + 处理指示
- done：绿色麦克风 + 对勾指示
- 用 SVG 设计后导出 PNG

### App 图标
- 1024×1024 主图，清新风格，麦克风主题
- 用 `iconutil` 从 iconset 生成 .icns
- 需要尺寸：16, 32, 64, 128, 256, 512, 1024（各含 @2x）

## 6. 构建脚本

文件：`scripts/build_dmg.sh`

```bash
#!/bin/bash
set -euo pipefail

# 环境变量
# DEVELOPER_ID_APPLICATION  - 签名 identity, e.g. "Developer ID Application: Name (TEAMID)"
# APPLE_ID                  - 公证用 Apple ID
# APPLE_TEAM_ID             - Team ID
# APP_PASSWORD              - app-specific password for notarytool

# 从源码文件直接提取版本号，不依赖 pip install
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/ohmyvoice/__init__.py)
APP_NAME="OhMyVoice"
DMG_NAME="${APP_NAME}-${VERSION}-arm64.dmg"
APP_DIR="dist/${APP_NAME}.app"

# Step 1: Build Swift UI
cd ui && swift build -c release && cd ..

# Step 2: PyInstaller
pyinstaller ohmyvoice.spec --noconfirm

# Step 3: Post-build copy — resources and Swift binary
# PyInstaller datas 放到 _internal/，我们需要放到 Contents/Resources/
cp -R resources/icons  "${APP_DIR}/Contents/Resources/icons"
cp -R resources/sounds "${APP_DIR}/Contents/Resources/sounds" 2>/dev/null || true
cp resources/AppIcon.icns "${APP_DIR}/Contents/Resources/AppIcon.icns" 2>/dev/null || true
cp ui/.build/release/ohmyvoice-ui "${APP_DIR}/Contents/MacOS/"

# Step 4: Pre-flight check — @2x icons
for state in idle recording processing done; do
  if [ ! -f "${APP_DIR}/Contents/Resources/icons/mic_${state}@2x.png" ]; then
    echo "WARNING: missing mic_${state}@2x.png — Retina 显示会模糊"
  fi
done

# Step 5: Inside-out code signing
# 不用 --deep，逐层签名确保公证通过
# 5a: _internal/ 内所有可签名文件（PyInstaller 6.x 把依赖放这里）
# 包括 .so、.dylib 和无扩展名的 Mach-O 可执行文件（如 Python framework）
find "${APP_DIR}/Contents/MacOS/_internal" -type f \( -name '*.dylib' -o -name '*.so' -o -perm +111 \) | while read bin; do
  # 只签名 Mach-O 文件，跳过 .py/.pyc/数据文件
  if file "$bin" | grep -q "Mach-O"; then
    codesign --force --options runtime --sign "${DEVELOPER_ID_APPLICATION}" "$bin"
  fi
done

# 5b: Swift UI binary（不需要 Python 侧的宽松 entitlements）
codesign --force --options runtime \
  --sign "${DEVELOPER_ID_APPLICATION}" \
  "${APP_DIR}/Contents/MacOS/ohmyvoice-ui"

# 5c: Python 主可执行文件（需要宽松 entitlements 给 MLX）
codesign --force --options runtime \
  --sign "${DEVELOPER_ID_APPLICATION}" \
  --entitlements entitlements.plist \
  "${APP_DIR}/Contents/MacOS/ohmyvoice"

# 5d: 外层 bundle
codesign --force --options runtime \
  --sign "${DEVELOPER_ID_APPLICATION}" \
  --entitlements entitlements.plist \
  "${APP_DIR}"

# Step 6: Notarize（notarytool 需要 zip/dmg/pkg，不接受 bare .app）
ditto -c -k --keepParent "${APP_DIR}" "dist/${APP_NAME}.zip"
xcrun notarytool submit "dist/${APP_NAME}.zip" \
  --apple-id "${APPLE_ID}" \
  --team-id "${APPLE_TEAM_ID}" \
  --password "${APP_PASSWORD}" \
  --wait
rm "dist/${APP_NAME}.zip"

# Step 7: Staple
xcrun stapler staple "${APP_DIR}"

# Step 8: Create DMG
rm -f "dist/${DMG_NAME}"
create-dmg \
  --volname "${APP_NAME}" \
  --window-size 600 400 \
  --icon-size 128 \
  --icon "${APP_NAME}.app" 150 200 \
  --app-drop-link 450 200 \
  "dist/${DMG_NAME}" \
  "${APP_DIR}"

# Step 9: Sign and notarize DMG
codesign --sign "${DEVELOPER_ID_APPLICATION}" "dist/${DMG_NAME}"
xcrun notarytool submit "dist/${DMG_NAME}" \
  --apple-id "${APPLE_ID}" \
  --team-id "${APPLE_TEAM_ID}" \
  --password "${APP_PASSWORD}" \
  --wait
xcrun stapler staple "dist/${DMG_NAME}"
```

## 7. Entitlements

两份 entitlements 文件，分别用于 Python 主进程和 Swift UI 子进程。

### `entitlements.plist`（Python 主进程，宽松权限给 MLX）

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

说明：
- `audio-input`：麦克风权限
- `apple-events`：剪贴板操作可能需要
- `allow-jit`：MLX Metal JIT 内核编译需要（hardened runtime 下必须显式声明）
- `allow-unsigned-executable-memory`：MLX Metal JIT 编译需要
- `disable-library-validation`：PyInstaller 打包的 dylib 签名链不完整时需要

### Swift UI 子进程

`ohmyvoice-ui` 不需要额外 entitlements，签名时不指定 `--entitlements`。它不直接访问麦克风或 Metal JIT，只通过 stdin/stdout 与 Python 进程通信。

## 8. Makefile 扩展

```makefile
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/ohmyvoice/__init__.py)

dist: build-swift
	pyinstaller ohmyvoice.spec --noconfirm
	cp -R resources/icons dist/OhMyVoice.app/Contents/Resources/icons
	cp -R resources/sounds dist/OhMyVoice.app/Contents/Resources/sounds 2>/dev/null || true
	cp ui/.build/release/ohmyvoice-ui dist/OhMyVoice.app/Contents/MacOS/

app: dist  # alias

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

## 9. 新增依赖

`pyproject.toml` 新增 optional group：

```toml
[project.optional-dependencies]
dist = [
    "pyinstaller>=6.0",
]
```

外部工具（非 pip）：
- `create-dmg`：`brew install create-dmg`
- Xcode Command Line Tools（已有）

## 10. 文件清单

新增文件：
- `ohmyvoice.spec` — PyInstaller 配置
- `entitlements.plist` — 代码签名 entitlements
- `scripts/build_dmg.sh` — 完整构建脚本
- `src/ohmyvoice/paths.py` — 资源路径解析
- `resources/AppIcon.icns` — app 图标

修改文件：
- `src/ohmyvoice/app.py` — 图标路径改用 `paths.get_resources_dir()`
- `src/ohmyvoice/audio_feedback.py` — 音效路径改用 `paths.get_resources_dir()`
- `src/ohmyvoice/autostart.py` — frozen 状态下用 `open` 命令启动 .app
- `resources/icons/*` — 新设计的菜单栏图标
- `Makefile` — 新增 dist/sign/notarize/dmg targets
- `pyproject.toml` — 新增 dist optional group
