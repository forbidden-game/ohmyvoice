# OhMyVoice — 产品设计规格

macOS 本地语音转文字工具。按住快捷键说话，松开后经 Qwen3-ASR 本地识别，结果写入剪贴板。

---

## 1. 产品定位

| 项目 | 内容 |
|------|------|
| 平台 | macOS (Apple Silicon, M1+) |
| 形态 | Menu bar 常驻应用 |
| 核心场景 | 开发者与 coding agent 协作时的语音输入，中英技术术语密集混杂 |
| 核心交互 | 按住快捷键 → 说话 → 松开 → 文字进剪贴板 |
| 离线能力 | 全本地推理，不依赖网络 |
| 硬件约束 | M1 16GB 可流畅运行 |

## 2. 技术架构

### 2.1 ASR 引擎

**模型：Qwen3-ASR-0.6B (4-bit, MLX)**

- 架构：AuT 音频编码器 (180M) + Qwen3 LLM 解码器 (~420M)
- 内置语言理解——不是纯声学模型，LLM 解码器带有世界知识和语义纠错能力
- 支持 system prompt 注入，可以通过 prompt 引导技术术语识别
- 内存占用：~680MB (4-bit)
- 推理速度：10 秒音频约 1-2 秒处理 (M1, 4-bit)
- MLX 实现：`mlx-qwen3-asr` (pip install)

**为什么不用 SenseVoice + LLM 纠错管线：**

- Qwen3-ASR 已内置 LLM 解码器，再叠加独立 LLM 是用弱模型纠正强模型
- LLM 纠错在低错误率区间有 3-12% 幻觉率，技术术语反而被改错
- 单模型更简单、更轻、延迟更低

### 2.2 应用架构

单进程 Python 应用：

```
┌────────────────────────────────────────────┐
│            OhMyVoice (Python)              │
│                                            │
│  ┌───────────┐  ┌───────────┐  ┌────────┐ │
│  │ HotkeyMgr │→ │ Recorder  │→ │  ASR   │ │
│  │ (PyObjC)  │  │(sounddev) │  │ (MLX)  │ │
│  └───────────┘  └───────────┘  └───┬────┘ │
│                                    ↓      │
│  ┌───────────┐  ┌───────────┐  ┌────────┐ │
│  │  MenuBar  │← │  History  │← │Clipbrd │ │
│  │  (rumps)  │  │ (SQLite)  │  │(PyObjC)│ │
│  └───────────┘  └───────────┘  └────────┘ │
│                                            │
│  ┌───────────┐  ┌───────────┐              │
│  │  Settings  │  │  Audio    │              │
│  │  (JSON)   │  │ Feedback  │              │
│  └───────────┘  └───────────┘              │
└────────────────────────────────────────────┘
```

**关键依赖：**

| 组件 | 库 | 用途 |
|------|----|------|
| ASR 推理 | `mlx-qwen3-asr` | Qwen3-ASR on MLX |
| 音频录制 | `sounddevice` | 跨平台音频 I/O |
| 全局快捷键 | `PyObjC` (Quartz, CGEventTap) | macOS 全局热键监听，需辅助功能权限 |
| 剪贴板 | `PyObjC` (AppKit.NSPasteboard) | 写入剪贴板 |
| Menu bar | `rumps` | macOS 状态栏应用 |
| 历史存储 | `sqlite3` (标准库) | 转写记录持久化 |
| 设置存储 | JSON 文件 | `~/.config/ohmyvoice/settings.json` |
| 音效 | `PyObjC` (AppKit.NSSound) | 提示音播放 |

**为什么选纯 Python 而非 Python + SwiftUI：**

- UI 需求极简（menu bar + 设置窗口），rumps 足够
- 单进程部署、调试更简单
- `mlx-qwen3-asr` 是 Python 包，无需跨语言调用
- 如果后续需要更丰富 UI，可以升级到 SwiftUI 壳

### 2.3 技术栈决策记录

**放弃方案：**

| 方案 | 放弃原因 |
|------|---------|
| SenseVoice + Qwen2.5-3B 管线 | Qwen3-ASR 已内置 LLM，管线冗余且有幻觉风险 |
| Paraformer + 热词列表 | 需维护词表，遇到新术语仍出错，不如 Qwen3-ASR 的 prompt |
| SwiftUI + Python 双进程 | 增加复杂度，当前 UI 需求不需要 |
| Electron / Tauri | 资源开销大，不适合常驻后台工具 |

## 3. 功能规格

### 3.1 核心功能

#### F1: 按住说话 (Push-to-Talk)

- 用户按住可配置的全局快捷键开始录音
- 松开快捷键结束录音并触发 ASR
- 默认快捷键：`⌥ Space`
- 录音期间 menu bar 图标变为红色脉冲 + 声波动画
- 支持最长录音时间限制（默认 60 秒，可配置）

#### F2: ASR 转写

- 松开快捷键后立即开始推理
- Menu bar 图标变为紫色旋转（处理中）
- 使用用户配置的 system prompt 引导识别
- 完成后文字写入系统剪贴板
- Menu bar 图标变为绿色 ✓（已复制），1 秒后回到空闲状态
- 同时写入历史记录数据库

#### F3: 自定义快捷键

- 设置窗口中可点击热键区域重新录制快捷键
- 支持修饰键 + 普通键的组合（如 ⌘⇧R, ⌃Space 等）
- 冲突处理：macOS 无全局热键冲突检测 API，采用 best-effort 方式——注册成功即可用，如果用户反馈无响应，设置界面提示"可能与其他应用冲突"
- 热键变更即时生效，无需重启

#### F4: System Prompt / 领域词表

- 设置窗口中提供文本输入框，用户可以编写 prompt
- 预设模板："编程对话"、"会议记录"、"日常口语"
- prompt 直接传给 Qwen3-ASR 的 `--prompt` 参数
- 示例默认 prompt："这是一位程序员对 coding agent 的口述指令。内容涉及 React、TypeScript、Python、API 设计等技术话题，包含大量英文技术术语。"

#### F5: 转写历史

- SQLite 存储，字段：id, text, duration_seconds, created_at
- Menu bar 下拉面板显示最近 3-5 条
- 设置窗口 → 历史 tab：完整历史列表，支持搜索
- 点击历史记录重新复制到剪贴板
- 最多保留 1000 条，自动清理最旧记录
- 支持手动清空

#### F6: 麦克风选择

- 设置窗口 → 音频 tab：下拉列表显示所有可用音频输入设备
- 默认选择系统默认输入设备
- 切换即时生效
- 设备拔插时自动刷新列表，断开时回退到系统默认

### 3.2 增强功能

#### F7: 音效反馈

- 开始录音时播放轻微"叮"声
- 完成转写 + 复制后播放不同的确认音
- 设置窗口中可开关（默认开启）
- 使用系统音效或自定义音效文件

#### F8: 开机自启

- 设置窗口中开关（默认关闭）
- 使用 macOS Login Items API (SMAppService)
- 通过 PyObjC 调用或 launchd plist

#### F9: 语言偏好

- 设置窗口 → 通用 tab：下拉选择
- 选项：自动检测 / 中文为主 / 英文为主
- 影响 Qwen3-ASR 的语言提示参数
- 自动检测适合中英混合场景（默认）

#### F10: 模型管理

- 设置窗口 → 模型 tab
- 显示：模型名称、量化精度、文件大小、内存占用
- 模型状态：已加载 / 未加载 / 加载中
- 首次启动时自动下载模型（显示进度），通过 `mlx-qwen3-asr` 内置的 HuggingFace Hub 下载机制
- 支持切换量化精度（4-bit / 8-bit），需重新加载模型

## 4. UI 设计

### 4.1 设计语言

| 属性 | 值 |
|------|----|
| 风格 | Industrial/Utilitarian + Refined |
| 主题 | 深色 |
| 品牌色 | Terracotta `#e07a5f` |
| 字体 (标签/代码) | JetBrains Mono |
| 字体 (正文/UI) | Outfit (或系统字体 fallback) |
| 背景 | 多层深色 `#0a0a0f` → `#111118` → `#1a1a24` |
| 纹理 | 轻微 noise texture 叠加 |
| 圆角 | 6/10/14/18px 四级 |
| 状态颜色 | 空闲=灰, 录音=红 `#ef4444`, 处理=紫 `#a78bfa`, 完成=绿 `#34d399` |

### 4.2 Menu Bar 图标

- 空闲：灰色麦克风 SF Symbol (`mic.fill`)
- 录音中：红色麦克风，menu bar 级别不做动画（系统限制）
- 处理中：紫色麦克风
- 完成：绿色对勾，1 秒后回到灰色

### 4.3 Menu Bar 下拉面板

从上到下：
1. **状态区**：圆形 orb 图标 + 状态文字 + 快捷键提示 + 模型状态徽章
2. **历史区**：最近 3 条转写记录，悬停显示复制按钮，点击复制
3. **底栏**：设置入口 (⌘,) + 全部历史入口

### 4.4 设置窗口

- macOS 原生窗口 chrome（traffic light 按钮、标题栏）
- 左侧固定导航：通用、音频、模型、Prompt、历史、关于
- 右侧内容区：分组展示设置项
- ⌘, 快捷键打开

### 4.5 状态流转

```
空闲 (灰) ──按住快捷键──→ 录音中 (红, 脉冲+声波)
                              │
                          松开快捷键
                              │
                              ↓
                         处理中 (紫, 旋转)
                              │
                          推理完成
                              │
                              ↓
                     已复制 (绿, ✓) ──1s──→ 空闲 (灰)
```

## 5. 数据模型

### 5.1 设置 (settings.json)

```json
{
  "hotkey": {
    "modifiers": ["option"],
    "key": "space"
  },
  "audio": {
    "input_device": null,
    "sound_feedback": true,
    "max_recording_seconds": 60
  },
  "model": {
    "name": "Qwen3-ASR-0.6B",
    "quantization": "4bit",
    "path": "~/.cache/ohmyvoice/models/"
  },
  "prompt": {
    "active_template": "coding",
    "custom_prompt": "",
    "templates": {
      "coding": "这是一位程序员对 coding agent 的口述指令。内容涉及 React、TypeScript、Python、API 设计等技术话题，包含大量英文技术术语。",
      "meeting": "这是一段会议讨论录音，可能涉及多人发言。",
      "general": ""
    }
  },
  "language": "auto",
  "autostart": false,
  "notification_on_complete": false,  // 预留，V1 暂不实现独立通知功能
  "history_max_entries": 1000
}
```

### 5.2 历史记录 (SQLite)

```sql
CREATE TABLE transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_transcriptions_created_at ON transcriptions(created_at DESC);
```

存储位置：`~/.local/share/ohmyvoice/history.db`

## 6. 交互细节

### 6.1 首次启动

1. 模型不存在 → 显示下载进度（menu bar 下拉面板内）
2. 请求麦克风权限（macOS 系统弹窗）
3. 请求辅助功能权限（用于全局快捷键，macOS 系统弹窗）
4. 模型加载完成 → 状态变为"就绪"

### 6.2 错误处理

| 场景 | 行为 |
|------|------|
| 麦克风权限未授予 | Menu bar 下拉显示提示，引导用户去系统设置 |
| 录音设备断开 | 自动回退到系统默认设备，通知用户 |
| ASR 推理失败 | Menu bar 图标变为黄色警告，下拉显示错误信息 |
| 模型未加载 | 快捷键按下时 menu bar 提示"模型加载中" |

### 6.3 性能预期

| 指标 | 目标 |
|------|------|
| 冷启动（含模型加载）| < 10 秒 |
| 热启动（模型已缓存）| < 3 秒 |
| 录音延迟 | < 50ms (音频框架延迟) |
| ASR 推理（10s 音频）| < 2 秒 (M1, 4-bit) |
| 内存常驻 | < 1GB (模型 680MB + 应用 ~200MB) |
| CPU 空闲时 | < 1% |

## 7. 文件结构（预期）

```
ohmyvoice-app/
├── src/
│   ├── __init__.py
│   ├── app.py              # 入口，rumps 应用
│   ├── hotkey.py            # 全局快捷键管理
│   ├── recorder.py          # 音频录制
│   ├── asr.py               # Qwen3-ASR 推理封装
│   ├── clipboard.py         # 剪贴板操作
│   ├── history.py           # SQLite 历史管理
│   ├── settings.py          # 设置读写
│   ├── audio_feedback.py    # 音效播放
│   └── model_manager.py     # 模型下载/加载/切换
├── resources/
│   ├── icons/               # menu bar 状态图标
│   └── sounds/              # 提示音文件
├── tests/
├── pyproject.toml
└── README.md
```

## 8. 无关范围 (Out of Scope for V1)

- 实时转写（边说边出字）
- 多人说话分离 (speaker diarization)
- 语音翻译
- 云端 API 集成
- iOS / Windows 版本
- 输入法模式（直接输入到光标）
- 口语转书面语润色
- 自定义唤醒词
