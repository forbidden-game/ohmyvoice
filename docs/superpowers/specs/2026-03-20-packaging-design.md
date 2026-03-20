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
    │   └── ohmyvoice-ui        # Swift 编译产物
    ├── Resources/
    │   ├── icons/
    │   │   ├── mic_idle.png
    │   │   ├── mic_idle@2x.png
    │   │   ├── mic_recording.png
    │   │   ├── mic_recording@2x.png
    │   │   ├── mic_processing.png
    │   │   ├── mic_processing@2x.png
    │   │   ├── mic_done.png
    │   │   └── mic_done@2x.png
    │   ├── sounds/
    │   └── AppIcon.icns
    └── Frameworks/             # PyInstaller 放 dylib
```

## 3. PyInstaller .spec 文件

文件：`ohmyvoice.spec`（项目根目录）

关键配置：
- **入口**：`src/ohmyvoice/__main__.py`
- **datas**：`resources/icons` → `Contents/Resources/icons`，`resources/sounds` → `Contents/Resources/sounds`
- **binaries**：`ui/.build/release/ohmyvoice-ui` → `Contents/MacOS/`
- **hiddenimports**：`mlx`、`mlx.core`、`mlx.nn`、`mlx_qwen3_asr`、`sounddevice`、`_sounddevice_data`、`rumps`、`numpy`、`huggingface_hub`
- **excludes**：`pytest`、`_pytest`、`coverage`、`pip`、`setuptools`
- **BUNDLE** 参数：`name='OhMyVoice'`、`bundle_identifier='com.ohmyvoice.app'`、`icon='resources/AppIcon.icns'`
- **Info.plist 覆盖**：
  - `NSMicrophoneUsageDescription`：语音转文字需要访问麦克风
  - `LSUIElement`：`True`（无 Dock 图标，纯菜单栏应用）

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

frozen 状态下，plist 的 `ProgramArguments` 改为：

```python
if getattr(sys, "frozen", False):
    # .app bundle: Contents/MacOS/ohmyvoice → 向上两级得到 .app 路径
    app_path = str(Path(sys.executable).parent.parent.parent)
    return f"""...
    <array>
        <string>open</string>
        <string>{app_path}</string>
    </array>
    ..."""
```

用 `open` 命令启动 .app bundle，macOS 会正确处理单实例和激活。

### 4c. ui_bridge.py

不需要改。已有 frozen 检测逻辑（`ui_bridge.py:67-71`），会在 `sys.executable` 同目录找 `ohmyvoice-ui`。

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

VERSION=$(python -c "from ohmyvoice import __version__; print(__version__)")
APP_NAME="OhMyVoice"
DMG_NAME="${APP_NAME}-${VERSION}-arm64.dmg"

# Step 1: Build Swift UI
cd ui && swift build -c release && cd ..

# Step 2: PyInstaller
pyinstaller ohmyvoice.spec --noconfirm

# Step 3: Copy Swift binary into bundle
cp ui/.build/release/ohmyvoice-ui "dist/${APP_NAME}.app/Contents/MacOS/"

# Step 4: Sign (递归签名所有 binary/dylib/framework)
codesign --deep --force --options runtime \
  --sign "${DEVELOPER_ID_APPLICATION}" \
  --entitlements entitlements.plist \
  "dist/${APP_NAME}.app"

# Step 5: Notarize
xcrun notarytool submit "dist/${APP_NAME}.app" \
  --apple-id "${APPLE_ID}" \
  --team-id "${APPLE_TEAM_ID}" \
  --password "${APP_PASSWORD}" \
  --wait

# Step 6: Staple
xcrun stapler staple "dist/${APP_NAME}.app"

# Step 7: Create DMG
create-dmg \
  --volname "${APP_NAME}" \
  --window-size 600 400 \
  --icon-size 128 \
  --icon "${APP_NAME}.app" 150 200 \
  --app-drop-link 450 200 \
  "dist/${DMG_NAME}" \
  "dist/${APP_NAME}.app"

# Step 8: Sign DMG
codesign --sign "${DEVELOPER_ID_APPLICATION}" "dist/${DMG_NAME}"
```

## 7. Entitlements

文件：`entitlements.plist`（项目根目录）

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
- `allow-unsigned-executable-memory`：MLX Metal JIT 编译需要
- `disable-library-validation`：PyInstaller 打包的 dylib 签名链不完整时需要

## 8. Makefile 扩展

```makefile
dist: build-swift
	pyinstaller ohmyvoice.spec --noconfirm
	cp ui/.build/release/ohmyvoice-ui dist/OhMyVoice.app/Contents/MacOS/

app: dist  # alias

sign:
	codesign --deep --force --options runtime \
		--sign "$(DEVELOPER_ID_APPLICATION)" \
		--entitlements entitlements.plist \
		dist/OhMyVoice.app

notarize:
	xcrun notarytool submit dist/OhMyVoice.app \
		--apple-id "$(APPLE_ID)" --team-id "$(APPLE_TEAM_ID)" \
		--password "$(APP_PASSWORD)" --wait
	xcrun stapler staple dist/OhMyVoice.app

dmg: dist sign notarize
	create-dmg --volname OhMyVoice --window-size 600 400 \
		--icon-size 128 --icon OhMyVoice.app 150 200 \
		--app-drop-link 450 200 \
		dist/OhMyVoice-$(VERSION)-arm64.dmg dist/OhMyVoice.app
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
