# omaboard-voice

Push-to-talk voice input daemon for Omarchy/Hyprland.

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
npm install
npm run build
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

```ini
[Unit]
Description=Omaboard voice daemon
After=network-online.target omaboard-voice-tunnel.service
Wants=network-online.target omaboard-voice-tunnel.service

[Service]
Type=simple
WorkingDirectory=/path/to/omaboard
Environment=VOICE_ENDPOINT=http://127.0.0.1:18000/v1/chat/completions
Environment=VOICE_MODEL=qwen3-asr
Environment=VOICE_LANGUAGE=zh
Environment="VOICE_RECORD_ARGS=--rate 16000 --channels 1 --target <your-mic-source-name>"
ExecStart=/usr/bin/env node /path/to/omaboard/dist/daemon.js
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
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
- For startup without login session, run `sudo loginctl enable-linger $USER`.

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
```

This server accepts OpenAI `/v1/chat/completions` payload and always returns mock text.

## License

MIT. See [LICENSE](./LICENSE).
