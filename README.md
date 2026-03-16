# omarvoice

Push-to-talk voice input daemon for Linux (Omarchy/Hyprland) and macOS.

## Demo

https://github.com/user-attachments/assets/80bbe068-f270-4904-91ab-25bc9aeefd01

- Tip: GitHub video is muted by default. Click the speaker icon to turn on sound.
- Fallback playback/download: [assets/demo.mp4](./assets/demo.mp4)

## Prerequisites

### Linux (Wayland/Hyprland)

- Node.js 20+
- Wayland desktop session (Hyprland)
- PipeWire tools: `pw-record`, `pw-play`
- `wl-clipboard` (`wl-copy`)
- `libnotify` (`notify-send`)

Preflight check (recommended before install):

```bash
set -euo pipefail
for cmd in node npm pw-record pw-play wl-copy notify-send systemctl; do
  command -v "$cmd" >/dev/null || { echo "Missing command: $cmd" >&2; exit 1; }
done
echo "All required commands are available."
```

### macOS

- Node.js 20+ (`brew install node`)
- ffmpeg (`brew install ffmpeg`) — for audio recording via AVFoundation
- Hammerspoon (optional, `brew install --cask hammerspoon`) — for global push-to-talk hotkey

All other tools (`afplay`, `pbcopy`, `osascript`) are built into macOS. Defaults auto-detect platform.

## Features

- Press hotkey -> start recording (`pw-record`)
- Release hotkey -> stop recording and submit to OpenAI-compatible ASR backend
- Copy transcript directly to clipboard (`wl-copy`)
- Show desktop notification (`notify-send`)
- Play start/stop prompt sounds
- Remove common filler words (`呃` / standalone `恶`) before copying
- Strict state machine: `idle -> recording -> submitting -> idle`
- On timeout or empty transcript, retry once automatically

## Install

```bash
npm ci
npm run build
```

Install `voicectl` globally only if your hotkey config calls `voicectl`:

```bash
npm link
```

## Quick Run

1. Start daemon:

```bash
VOICE_ENDPOINT=http://127.0.0.1:8000/v1/chat/completions node dist/daemon.js
```

2. Trigger manually:

```bash
node dist/cli.js start
# speak...
node dist/cli.js stop
```

If successful, transcript text is copied to clipboard.

For a deterministic local smoke test without external ASR:

```bash
node examples/mock-backend.mjs
VOICE_ENDPOINT=http://127.0.0.1:8787/v1/chat/completions node dist/daemon.js
```

## macOS Hotkey (Hammerspoon)

Copy `contrib/macos/omarvoice.lua` into `~/.hammerspoon/init.lua` (or source it). Edit `nodeBin` and `cliScript` to match your install paths. Requires Accessibility permission in System Settings > Privacy & Security.

Hold F1 to record, release to stop. See the Lua file for details.

## Omarchy / Hyprland Hotkey

Use key press to start and key release to stop. Current recommended single-key mapping is `CapsLock` (`code:66`):

```ini
bind = , code:66, exec, voicectl start
bindr = , code:66, exec, voicectl stop
```

Reload Hyprland after editing:

```bash
hyprctl reload
```

## Autostart With systemd User Services (Recommended)

If your ASR backend is remote, use a local SSH tunnel plus local daemon.
The service file must use absolute paths.

Find your absolute project path:

```bash
realpath .
```

1. Create `~/.config/systemd/user/omarvoice-tunnel.service`:

```ini
[Unit]
Description=Omarvoice SSH tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -N -L 18000:127.0.0.1:8000 <your-ssh-host-alias> -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

2. Create `~/.config/systemd/user/omarvoice.service`:

Find absolute paths first (optional: list sources only if you want to pin a specific microphone):

```bash
realpath .
command -v node
pactl list short sources
```

```ini
[Unit]
Description=Omarvoice daemon
After=graphical-session.target network-online.target omarvoice-tunnel.service
Wants=network-online.target omarvoice-tunnel.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=/absolute/path/to/omarvoice
Environment=VOICE_ENDPOINT=http://127.0.0.1:18000/v1/chat/completions
Environment=VOICE_MODEL=Qwen/Qwen3-ASR-1.7B
Environment=VOICE_LANGUAGE=zh
Environment="VOICE_RECORD_ARGS=--rate 16000 --channels 1"
ExecStart=/absolute/path/to/node /absolute/path/to/omarvoice/dist/daemon.js
Restart=always
RestartSec=2

[Install]
WantedBy=graphical-session.target
```

3. Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now omarvoice-tunnel.service
systemctl --user enable --now omarvoice.service
```

4. Verify:

```bash
systemctl --user status omarvoice.service omarvoice-tunnel.service
voicectl status
```

Notes:

- `enabled` user services auto-start after you log in.
- `omarvoice.service` requires an active graphical Wayland session (`graphical-session.target`).
- `sudo loginctl enable-linger $USER` is only suitable for non-graphical services such as the SSH tunnel.

## macOS LaunchAgent (Autostart)

Copy the example plist and edit absolute paths:

```bash
cp contrib/macos/com.omarvoice.daemon.plist ~/Library/LaunchAgents/
# Edit paths in the plist to match your install
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.omarvoice.daemon.plist
launchctl kickstart -k gui/$(id -u)/com.omarvoice.daemon
```

To remove or before re-installing: `launchctl bootout gui/$(id -u)/com.omarvoice.daemon`

**Important:** `launchctl` runs with an empty PATH. The plist sets absolute paths for node and includes `/opt/homebrew/bin` in PATH for ffmpeg.

## Troubleshooting

- `voicectl` command not found:
  - Run `npm link`, then verify with `which voicectl`.
- Daemon cannot connect to backend:
  - Check `VOICE_ENDPOINT` and test with `curl`.
  - Check logs with `journalctl --user -u omarvoice.service -f`.
- SSH tunnel service restarts or hangs:
  - Ensure key-based SSH login is configured for `<your-ssh-host-alias>`.
  - Test non-interactive SSH first: `ssh -o BatchMode=yes <your-ssh-host-alias> true`.
- No transcript copied to clipboard:
  - Confirm `wl-copy` exists: `which wl-copy`.
  - If you see `Failed to connect to a Wayland server`, make sure `omarvoice.service` is started in `graphical-session.target` (not `default.target`) so `WAYLAND_DISPLAY` is available.
- Microphone not recording:
  - Confirm PipeWire tools exist: `which pw-record`.
  - List valid sources with `pactl list short sources`; if needed, pin one source in `VOICE_RECORD_ARGS` by adding `--target <source-name>`.

### macOS

- **Microphone permission**: ffmpeg needs Microphone access — grant in System Settings > Privacy & Security > Microphone for Terminal / iTerm / whichever app runs the daemon. Run the daemon once from an interactive terminal first to trigger the macOS permission prompt before switching to LaunchAgent.
- **Accessibility permission**: Hammerspoon needs Accessibility for global hotkey capture — grant in System Settings > Privacy & Security > Accessibility.
- **LaunchAgent PATH**: If daemon can't find ffmpeg, check `/tmp/omarvoice.stderr.log`; ensure absolute paths in plist and that PATH includes `/opt/homebrew/bin`.
- **AVFoundation device selection**: Use device index (`:0`, `:1`), not device name. Find indices with `ffmpeg -f avfoundation -list_devices true -i ""`.
- **WireGuard**: Backend at 10.66.0.3:8000 requires active WireGuard tunnel.

## Environment Variables

Defaults auto-detect platform. Linux defaults shown first; macOS defaults in parentheses.

- `VOICE_ENDPOINT`: OpenAI-compatible chat completions endpoint.
- `VOICE_API_KEY`: optional bearer token.
- `VOICE_SOCKET_PATH`: Unix socket path. Default: `$XDG_RUNTIME_DIR/omarvoice.sock` (macOS: `/tmp/omarvoice.sock`).
- `VOICE_TMP_DIR`: temp wav dir. Default: `/tmp`.
- `VOICE_RECORD_COMMAND`: recorder command. Default: `pw-record` (macOS: `ffmpeg`).
- `VOICE_RECORD_ARGS`: recorder args. Default: `--rate 16000 --channels 1` (macOS: `-f avfoundation -i :default -ar 16000 -ac 1 -y`).
- `VOICE_START_SOUND_COMMAND`: start prompt command. Default: `pw-play` (macOS: `afplay`).
- `VOICE_START_SOUND_ARGS`: start prompt args. Default: `--volume 0.35 /usr/.../bell.oga` (macOS: `-v 0.35 /System/Library/Sounds/Tink.aiff`).
- `VOICE_STOP_SOUND_COMMAND`: stop prompt command. Default: `pw-play` (macOS: `afplay`).
- `VOICE_STOP_SOUND_ARGS`: stop prompt args. Default: `--volume 0.35 /usr/.../complete.oga` (macOS: `-v 0.35 /System/Library/Sounds/Glass.aiff`).
- `VOICE_CLIPBOARD_COMMAND`: clipboard command. Default: `wl-copy` (macOS: `pbcopy`).
- `VOICE_NOTIFY_COMMAND`: notification command. Default: `notify-send` (macOS: `osascript`).
- `VOICE_MODEL`: request model. Default: `Qwen/Qwen3-ASR-1.7B`.
- `VOICE_PROMPT`: prompt text.
- `VOICE_LANGUAGE`: optional language hint appended to prompt.
- `VOICE_MAX_TOKENS`: `max_tokens` in request body. Default: `1024`.
- `VOICE_REQUEST_TIMEOUT_MS`: timeout in ms. Default: `45000`.

## Development

Run all checks:

```bash
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
```

## Local Mock Backend (Smoke Test)

```bash
node examples/mock-backend.mjs
VOICE_ENDPOINT=http://127.0.0.1:8787/v1/chat/completions node dist/daemon.js
# In another shell:
node dist/cli.js start
# speak...
node dist/cli.js stop
```

This server listens on `127.0.0.1:8787`, accepts OpenAI `/v1/chat/completions` payload, and always returns mock text.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT. See [LICENSE](./LICENSE).
