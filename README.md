<p align="center">
  <img src="assets/icon.png" width="128" alt="ohmyvoice icon" />
</p>

<h1 align="center">ohmyvoice</h1>

<p align="center">
  Push-to-talk voice input for your desktop.<br/>
  Hold a key, speak, release — transcript lands in your clipboard, ready to paste.
</p>

<p align="center">
  <strong>macOS</strong> · <strong>Linux (Wayland / Hyprland)</strong>
</p>

> **ohmyvoice 是一个完全本地化的语音输入工具。** 内置 SenseVoice 后端，开箱即用——录音、识别、剪贴板集成全部在本机完成，音频数据不出本地。也支持接入自建模型（Qwen3-ASR、Whisper 等）或任何兼容 OpenAI Chat Completions 接口的第三方 API。
>
> **ohmyvoice is a fully local voice input tool.** Ships with a bundled SenseVoice backend — recording, recognition, and clipboard integration all happen on your machine. Audio never leaves your device. You can also plug in your own ASR model or any OpenAI-compatible endpoint.

### Why Local?

- **Privacy first** — your voice stays on your machine. No audio uploaded to third-party servers.
- **Ownership & traceability** — all data is under your control, auditable and deletable at any time.
- **Lightweight** — SenseVoice-Small uses ~200 MB memory, processes 10 seconds of speech in ~70 ms.
- **Offline-capable** — works without internet once the model is downloaded.

---

## Demo

https://github.com/user-attachments/assets/80bbe068-f270-4904-91ab-25bc9aeefd01

> Video is muted by default — click the speaker icon. Fallback: [assets/demo.mp4](./assets/demo.mp4)

## How It Works

1. **Hold** the hotkey → recording starts (you hear a prompt sound)
2. **Speak** freely
3. **Release** the hotkey → audio is recognized locally by SenseVoice (or any OpenAI-compatible backend)
4. **Transcript** is copied to clipboard + desktop notification

That's it. No GUI, no electron app — just a lightweight daemon and a CLI.

### Under the Hood

- Strict state machine: `idle → recording → submitting → idle`
- Auto-retry on timeout or empty transcript
- Filler word cleanup (e.g. `呃`, stray punctuation)
- Platform-aware defaults — zero config on either OS

---

## Quick Start

### macOS

**1. Install dependencies**

```bash
brew install node ffmpeg python3
brew install --cask hammerspoon
```

**2. One-command setup**

```bash
git clone https://github.com/forbidden-game/ohmyvoice.git && cd ohmyvoice && ./setup-macos.sh
```

This builds the project, creates a local Python venv with SenseVoice dependencies, downloads the model (~228 MB), installs the Hammerspoon integration, and triggers the microphone permission prompt.

**3. Grant permissions**

- **Accessibility**: System Settings → Privacy & Security → Accessibility → Hammerspoon
- **Microphone**: System Settings → Privacy & Security → Microphone → Hammerspoon

**4. Use it**

Hold **Right Command** to record, release to stop. Transcript appears in your clipboard.

The SenseVoice backend starts and stops automatically with the daemon — no need to run `server.py` manually.

> **Why Hammerspoon?** macOS LaunchAgents lack the AudioSession context that ffmpeg's AVFoundation needs. Hammerspoon is a GUI app — processes it spawns get proper audio access. Without it you get sped-up, noisy recordings. See [contrib/macos/SETUP.md](contrib/macos/SETUP.md) for details.

---

### Linux (Wayland / Hyprland)

**1. Install dependencies**

```bash
# Arch / pacman
sudo pacman -S nodejs npm pipewire pw-record wl-clipboard libnotify

# Ubuntu / apt
sudo apt install nodejs npm pipewire-tools wl-clipboard libnotify-bin
```

Preflight check:

```bash
for cmd in node npm pw-record pw-play wl-copy notify-send; do
  command -v "$cmd" >/dev/null || echo "Missing: $cmd"
done
```

**2. Build**

```bash
git clone https://github.com/forbidden-game/ohmyvoice.git && cd ohmyvoice && npm ci && npm run build
```

**3. Start the daemon**

```bash
VOICE_ENDPOINT=http://127.0.0.1:8000/v1/chat/completions node dist/daemon.js
```

**4. Bind a hotkey** (Hyprland example — CapsLock)

Add to `~/.config/hypr/hyprland.conf`:

```ini
bind = , code:66, exec, voicectl start
bindr = , code:66, exec, voicectl stop
```

```bash
npm link          # makes voicectl available globally
hyprctl reload
```

Hold **CapsLock** to record, release to stop.

---

## Manual Trigger (Any Platform)

You can also trigger recording without a hotkey:

```bash
# Start daemon
VOICE_ENDPOINT=http://127.0.0.1:8000/v1/chat/completions node dist/daemon.js

# In another terminal
node dist/cli.js start   # begin recording
# speak...
node dist/cli.js stop    # stop and transcribe

node dist/cli.js status  # check daemon state
```

## Smoke Test (No ASR Needed)

```bash
node examples/mock-backend.mjs &
VOICE_ENDPOINT=http://127.0.0.1:8787/v1/chat/completions node dist/daemon.js
```

The mock server always returns a fixed transcript — useful for verifying your setup end-to-end.

---

## Autostart

<details>
<summary><strong>macOS — Hammerspoon</strong></summary>

Hammerspoon manages the daemon as a child process — no separate LaunchAgent needed. Add Hammerspoon to your Login Items (System Settings → General → Login Items) and the daemon starts automatically on login.

That's the whole setup. Hammerspoon handles both the hotkey and the daemon lifecycle.

> **Note:** A legacy `com.ohmyvoice.daemon.plist` exists in `contrib/macos/` but **should not be used** — LaunchAgents lack the AudioSession context required for proper audio capture, resulting in broken recordings.

</details>

<details>
<summary><strong>Linux — systemd user services</strong></summary>

If your ASR backend is remote, use a local SSH tunnel plus daemon service.

**SSH tunnel** — `~/.config/systemd/user/ohmyvoice-tunnel.service`:

```ini
[Unit]
Description=Ohmyvoice SSH tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -N -L 18000:127.0.0.1:8000 <your-ssh-host> \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

**Daemon** — `~/.config/systemd/user/ohmyvoice.service`:

```ini
[Unit]
Description=Ohmyvoice daemon
After=graphical-session.target network-online.target ohmyvoice-tunnel.service
Wants=network-online.target ohmyvoice-tunnel.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=/absolute/path/to/ohmyvoice
Environment=VOICE_ENDPOINT=http://127.0.0.1:18000/v1/chat/completions
Environment=VOICE_MODEL=Qwen/Qwen3-ASR-1.7B
Environment=VOICE_LANGUAGE=zh
Environment="VOICE_RECORD_ARGS=--rate 16000 --channels 1"
ExecStart=/absolute/path/to/node /absolute/path/to/ohmyvoice/dist/daemon.js
Restart=always
RestartSec=2

[Install]
WantedBy=graphical-session.target
```

Replace `/absolute/path/to/...` with real paths (`realpath .`, `command -v node`).

```bash
systemctl --user daemon-reload
systemctl --user enable --now ohmyvoice-tunnel.service
systemctl --user enable --now ohmyvoice.service
systemctl --user status ohmyvoice.service ohmyvoice-tunnel.service
```

Notes:

- `enabled` user services auto-start after login.
- The daemon service requires an active Wayland session (`graphical-session.target`).
- `sudo loginctl enable-linger $USER` is only for non-graphical services (e.g. the SSH tunnel).

</details>

---

## Configuration

All settings are environment variables. Defaults auto-detect your platform — most users need zero configuration.

| Variable                   | Description                                     | Default                                                                  |
| -------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------ |
| `VOICE_ENDPOINT`           | OpenAI-compatible chat completions URL          | `http://127.0.0.1:8000/v1/chat/completions`                              |
| `VOICE_BACKEND`            | `managed` (auto-start SenseVoice) or `external` | `managed` when using the default endpoint on macOS; `external` otherwise |
| `VOICE_API_KEY`            | Bearer token (if backend requires auth)         | _(none)_                                                                 |
| `VOICE_MODEL`              | Model name in request body                      | `Qwen/Qwen3-ASR-1.7B`                                                    |
| `VOICE_LANGUAGE`           | Language hint appended to prompt                | _(none)_                                                                 |
| `VOICE_PROMPT`             | Custom prompt text                              | _(built-in)_                                                             |
| `VOICE_MAX_TOKENS`         | `max_tokens` in request                         | `1024`                                                                   |
| `VOICE_REQUEST_TIMEOUT_MS` | Request timeout (ms)                            | `45000`                                                                  |

<details>
<summary>Platform-specific defaults (click to expand)</summary>

| Variable                    | Linux                                 | macOS                                                                                            |
| --------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `VOICE_SOCKET_PATH`         | `$XDG_RUNTIME_DIR/ohmyvoice.sock`     | `/tmp/ohmyvoice.sock`                                                                            |
| `VOICE_TMP_DIR`             | `/tmp`                                | `/tmp`                                                                                           |
| `VOICE_RECORD_COMMAND`      | `pw-record`                           | `ffmpeg`                                                                                         |
| `VOICE_RECORD_FILE_EXT`     | `.wav`                                | `.ogg`                                                                                           |
| `VOICE_RECORD_ARGS`         | `--rate 16000 --channels 1`           | `-f avfoundation -i :default -ar 16000 -ac 1 -c:a libopus -application voip -flush_packets 1 -y` |
| `VOICE_START_SOUND_COMMAND` | `pw-play`                             | `afplay`                                                                                         |
| `VOICE_START_SOUND_ARGS`    | `--volume 0.35 /usr/.../bell.oga`     | `-v 0.35 /System/.../Tink.aiff`                                                                  |
| `VOICE_STOP_SOUND_COMMAND`  | `pw-play`                             | `afplay`                                                                                         |
| `VOICE_STOP_SOUND_ARGS`     | `--volume 0.35 /usr/.../complete.oga` | `-v 0.35 /System/.../Glass.aiff`                                                                 |
| `VOICE_CLIPBOARD_COMMAND`   | `wl-copy`                             | `pbcopy`                                                                                         |
| `VOICE_NOTIFY_COMMAND`      | `notify-send`                         | `osascript`                                                                                      |

</details>

---

## Troubleshooting

### macOS

| Symptom                      | Fix                                                                                                               |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| No sound / sped-up audio     | Daemon must be launched by Hammerspoon (not standalone or via LaunchAgent). Also check audio device index.        |
| Clipboard garbled (CJK)      | Set `LANG=en_US.UTF-8` in daemon environment.                                                                     |
| Hotkey not working           | Grant Accessibility to Hammerspoon. Reload config after edits.                                                    |
| Microphone permission prompt | Run daemon once from an interactive terminal first.                                                               |
| `ffmpeg` not found           | Ensure `PATH` includes `/opt/homebrew/bin`.                                                                       |
| Wrong microphone             | List devices: `ffmpeg -f avfoundation -list_devices true -i ""`, then set `VOICE_RECORD_ARGS` with correct index. |

### Linux

| Symptom                        | Fix                                                                                                |
| ------------------------------ | -------------------------------------------------------------------------------------------------- |
| `voicectl` not found           | Run `npm link`, verify with `which voicectl`.                                                      |
| Cannot connect to backend      | Check `VOICE_ENDPOINT`, test with `curl`. Check logs: `journalctl --user -u ohmyvoice.service -f`. |
| SSH tunnel restarts            | Ensure key-based SSH: `ssh -o BatchMode=yes <host> true`.                                          |
| No clipboard                   | Confirm `wl-copy`: `which wl-copy`.                                                                |
| `Failed to connect to Wayland` | Start service under `graphical-session.target`, not `default.target`.                              |
| Microphone not recording       | Confirm `pw-record`: `which pw-record`. List sources: `pactl list short sources`.                  |

---

## Development

```bash
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT. See [LICENSE](./LICENSE).
