# omaboard-voice

Push-to-talk voice input daemon for Omarchy/Hyprland.

## Prerequisites

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

1. Create `~/.config/systemd/user/omaboard-voice-tunnel.service`:

```ini
[Unit]
Description=Omaboard voice SSH tunnel
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

2. Create `~/.config/systemd/user/omaboard-voice.service`:

Find absolute paths and microphone source first:

```bash
realpath .
command -v node
pw-record --list-targets
```

```ini
[Unit]
Description=Omaboard voice daemon
After=graphical-session.target network-online.target omaboard-voice-tunnel.service
Wants=network-online.target omaboard-voice-tunnel.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=/absolute/path/to/omaboard
Environment=VOICE_ENDPOINT=http://127.0.0.1:18000/v1/chat/completions
Environment=VOICE_MODEL=qwen3-asr
Environment=VOICE_LANGUAGE=zh
Environment="VOICE_RECORD_ARGS=--rate 16000 --channels 1 --target <your-mic-source-name>"
ExecStart=/absolute/path/to/node /absolute/path/to/omaboard/dist/daemon.js
Restart=always
RestartSec=2

[Install]
WantedBy=graphical-session.target
```

3. Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now omaboard-voice-tunnel.service
systemctl --user enable --now omaboard-voice.service
```

4. Verify:

```bash
systemctl --user status omaboard-voice.service omaboard-voice-tunnel.service
voicectl status
```

Notes:

- `enabled` user services auto-start after you log in.
- `omaboard-voice.service` requires an active graphical Wayland session (`graphical-session.target`).
- `sudo loginctl enable-linger $USER` is only suitable for non-graphical services such as the SSH tunnel.

## Troubleshooting

- `voicectl` command not found:
  - Run `npm link`, then verify with `which voicectl`.
- Daemon cannot connect to backend:
  - Check `VOICE_ENDPOINT` and test with `curl`.
  - Check logs with `journalctl --user -u omaboard-voice.service -f`.
- SSH tunnel service restarts or hangs:
  - Ensure key-based SSH login is configured for `<your-ssh-host-alias>`.
  - Test non-interactive SSH first: `ssh -o BatchMode=yes <your-ssh-host-alias> true`.
- No transcript copied to clipboard:
  - Confirm `wl-copy` exists: `which wl-copy`.
  - If you see `Failed to connect to a Wayland server`, make sure `omaboard-voice.service` is started in `graphical-session.target` (not `default.target`) so `WAYLAND_DISPLAY` is available.
- Microphone not recording:
  - Confirm PipeWire tools exist: `which pw-record`.
  - List valid targets with `pw-record --list-targets`, then set `VOICE_RECORD_ARGS` with a real source name.

## Environment Variables

- `VOICE_ENDPOINT`: OpenAI-compatible chat completions endpoint.
- `VOICE_API_KEY`: optional bearer token.
- `VOICE_SOCKET_PATH`: Unix socket path. Default: `$XDG_RUNTIME_DIR/omaboard-voice.sock`.
- `VOICE_TMP_DIR`: temp wav dir. Default: `/tmp`.
- `VOICE_RECORD_COMMAND`: recorder command. Default: `pw-record`.
- `VOICE_RECORD_ARGS`: recorder args. Default: `--rate 16000 --channels 1`.
- `VOICE_START_SOUND_COMMAND`: start prompt command. Default: `pw-play`.
- `VOICE_START_SOUND_ARGS`: start prompt args. Default: `/usr/share/sounds/freedesktop/stereo/bell.oga`.
- `VOICE_STOP_SOUND_COMMAND`: stop prompt command. Default: `pw-play`.
- `VOICE_STOP_SOUND_ARGS`: stop prompt args. Default: `/usr/share/sounds/freedesktop/stereo/complete.oga`.
- `VOICE_CLIPBOARD_COMMAND`: clipboard command. Default: `wl-copy`.
- `VOICE_NOTIFY_COMMAND`: notification command. Default: `notify-send`.
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
