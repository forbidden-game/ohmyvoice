# OhMyVoice 设置窗口 — 设计规格

macOS 原生设置窗口，替换当前 `rumps.Window` 文本输入框，暴露全部可配置项。

---

## 1. 架构决策

| 决策 | 结论 | 原因 |
|------|------|------|
| 窗口框架 | PyObjC NSWindow + NSToolbar | 原生 macOS 偏好设置范式，用户零学习成本 |
| Tab 数量 | 4（通用/音频/识别/关于） | 原方案 6 tab 过散；模型并入识别，历史设置并入通用 |
| 视觉风格 | 系统原生（跟随系统浅色/深色、系统字体、标准 AppKit 控件） | 工具类应用不需要品牌定制，减少维护成本 |
| 打开方式 | 菜单栏"设置..."菜单项 → 弹出独立 NSWindow | macOS 标准做法 |
| 与 app 关系 | 设置窗口关闭不影响菜单栏 app 运行 | 工具类应用惯例 |

## 2. 窗口规格

```
┌──────────────────────────────────────────┐
│ ● ● ●          OhMyVoice 设置            │  ← NSWindow titlebar
├──────────────────────────────────────────┤
│   ⚙ 通用   🎵 音频   ✨ 识别   ⓘ 关于    │  ← NSToolbar (selectable items)
├──────────────────────────────────────────┤
│                                          │
│         Tab 内容区 (NSView)               │  ← 内容随 tab 切换
│                                          │
└──────────────────────────────────────────┘
```

- 固定宽度：520pt
- 高度：随当前 tab 内容自适应
- 不可全屏，不可缩放（utility 窗口），可最小化
- 窗口标题："OhMyVoice 设置"
- 单实例：如果窗口已打开，再次点击"设置..."将 `makeKeyAndOrderFront` 置顶

## 3. Toolbar 定义

4 个 `NSToolbarItem`，每个包含图标 + 文字标签：

| ID | 标签 | SF Symbol | 说明 |
|----|------|-----------|------|
| `general` | 通用 | `gearshape` | 快捷键、行为、数据 |
| `audio` | 音频 | `waveform` | 麦克风、提示音、录音时长 |
| `recognition` | 识别 | `text.word.spacing` 或 `sparkles` | Prompt、量化精度 |
| `about` | 关于 | `info.circle` | 版本、模型状态、链接 |

选中态由 NSToolbar `selectedItemIdentifier` 管理（系统自动处理高亮）。

## 4. Tab 内容

### 4.1 通用

三个分组，每组有灰色小标题。

**快捷键**

| 控件 | 类型 | 行为 |
|------|------|------|
| 当前热键显示 | NSTextField (只读，居中，显示 "⌥ Space") | 展示当前快捷键 |
| "录制"按钮 | NSButton | 点击后进入捕获模式：按钮文字变为"按下新组合..."，监听下一个按键事件，捕获后更新设置并即时生效（调用 `HotkeyManager.update_hotkey`） |

**行为**

| 控件 | 类型 | 映射 |
|------|------|------|
| 语言偏好 | NSPopUpButton | `settings.language`，选项："自动检测" / "中文为主" / "英文为主" |
| 开机自启 | NSSwitch | `settings.autostart`，切换时调用 `autostart.enable()` / `autostart.disable()` |
| 完成通知 | NSSwitch | `settings.notification_on_complete` |

**数据**

| 控件 | 类型 | 映射 |
|------|------|------|
| 历史记录上限 | NSTextField + NSStepper | `settings.history_max_entries`，范围 100–5000，步长 100 |

### 4.2 音频

三个分组。

**输入**

| 控件 | 类型 | 行为 |
|------|------|------|
| 麦克风 | NSPopUpButton | 调用 `Recorder.list_input_devices()` 填充列表，首项"系统默认"（映射 `None`），选择后更新 `settings.input_device` 并重建 Recorder |

**反馈**

| 控件 | 类型 | 映射 |
|------|------|------|
| 提示音 | NSSwitch | `settings.sound_feedback` |

副标签："录音开始和转写完成时播放"

**录音**

| 控件 | 类型 | 映射 |
|------|------|------|
| 最长录音时间 | NSSlider + NSTextField (只读显示值) | `settings.max_recording_seconds`，范围 10–120 秒，连续滑动 |

### 4.3 识别

两个分组。

**Prompt 模板**

| 控件 | 类型 | 行为 |
|------|------|------|
| 当前模板 | NSPopUpButton | 选项："编程" / "会议" / "日常" / "自定义"，映射 `settings.active_prompt_template` |
| Prompt 内容 | NSTextView (等宽字体 SF Mono) | 预设模板时只读（灰色背景），选"自定义"时可编辑（白色背景），映射 `settings.custom_prompt` |

底部提示文字："选择"自定义"后可编辑内容，预设模板仅供预览"

**模型**

| 控件 | 类型 | 行为 |
|------|------|------|
| 量化精度 | NSPopUpButton | 选项："4-bit" / "8-bit"，映射 `settings.model_quantization` |

量化精度变更触发模型重载：
1. 显示警告文字 "⚠ 切换精度需要重新加载模型（约 5 秒）"
2. 用户确认后，后台线程执行 `engine.unload()` → `engine.load(quantize_bits=new_bits)`
3. 加载期间 menu bar 状态回到"加载中..."

### 4.4 关于

**App 信息**

居中展示：
- App 图标（72×72pt，麦克风图案）
- "OhMyVoice"
- "版本 X.Y.Z"（从 `pyproject.toml` 或 `__version__` 读取）

**模型**

| 行 | 内容 |
|----|------|
| 模型名 + 量化 | "Qwen3-ASR-0.6B (4-bit)" |
| 状态 | 绿色圆点 + "已加载" / 黄色圆点 + "加载中" / 灰色圆点 + "未加载" |
| 磁盘占用 | "680 MB"（读取缓存目录实际大小） |

**链接**

- "GitHub 项目主页" — 点击用 `NSWorkspace` 打开浏览器
- "反馈与建议" — 点击打开 GitHub Issues 页面

## 5. 数据流

```
用户操作控件
    ↓
控件回调 (target-action)
    ↓
更新 Settings 对象属性
    ↓
调用 Settings.save()  →  写入 ~/.config/ohmyvoice/settings.json
    ↓
如需即时生效:
  - 快捷键 → HotkeyManager.update_hotkey()
  - 麦克风 → 重建 Recorder
  - 开机自启 → autostart.enable()/disable()
  - 量化精度 → 重载模型
```

设置变更**即时保存、即时生效**，没有"应用"/"取消"按钮。这是 macOS 偏好设置的标准做法。

## 6. 实现要点

### 6.1 模块结构

新增 `src/ohmyvoice/preferences.py`：

```python
class PreferencesWindow:
    """NSWindow-based preferences, 4 toolbar tabs."""

    def __init__(self, app: OhMyVoiceApp):
        self._app = app           # 访问 settings, recorder, engine, hotkey
        self._window: NSWindow
        self._toolbar: NSToolbar
        self._views: dict[str, NSView]  # tab_id → content view

    def show(self):
        """显示或置顶窗口。"""

    def _build_window(self) -> NSWindow: ...
    def _build_toolbar(self) -> NSToolbar: ...
    def _build_general_view(self) -> NSView: ...
    def _build_audio_view(self) -> NSView: ...
    def _build_recognition_view(self) -> NSView: ...
    def _build_about_view(self) -> NSView: ...
    def _switch_tab(self, tab_id: str): ...
```

### 6.2 app.py 变更

- `_on_settings` 回调：从 `rumps.Window` 改为 `PreferencesWindow.show()`
- `PreferencesWindow` 持有对 app 的引用，通过 app 访问 settings / recorder / engine / hotkey

### 6.3 PyObjC 关键 API

| 需求 | API |
|------|-----|
| 窗口 | `NSWindow.alloc().initWithContentRect_styleMask_backing_defer_` |
| 工具栏 | `NSToolbar.alloc().initWithIdentifier_`，实现 `NSToolbarDelegate` |
| 开关 | `NSSwitch.alloc().initWithFrame_` (macOS 10.15+) |
| 下拉 | `NSPopUpButton.alloc().initWithFrame_pullsDown_` |
| 滑块 | `NSSlider.sliderWithValue_minValue_maxValue_target_action_` |
| 文本编辑 | `NSTextView` 嵌入 `NSScrollView` |
| 布局 | Auto Layout (`NSLayoutConstraint`) 或手动 frame 计算 |

### 6.4 线程安全

- 所有 UI 操作在主线程（`performSelectorOnMainThread` 或 `dispatch_async(dispatch_get_main_queue(), ...)`）
- 模型重载在后台 daemon 线程
- Settings.save() 是同步 I/O，在主线程调用即可（写入极快）

## 7. 不做的事

- 不做自定义深色主题 / 品牌色 / 自定义字体
- 不做窗口动画 / 过渡效果
- 不做 undo/redo（设置变更即时保存）
- 不做本地化（目前只有中文界面）
- 不做键盘快捷键打开设置（⌘, 需要 NSApplication menu bar，rumps 不支持）
- 不做设置导入/导出
