# macOS Setup Guide

## Quick Start

```bash
brew install node ffmpeg python3
brew install --cask hammerspoon

git clone https://github.com/forbidden-game/ohmyvoice.git && cd ohmyvoice && ./setup-macos.sh
```

The setup script handles building, Python venv, model download, and Hammerspoon integration. Grant **Accessibility** and **Microphone** to Hammerspoon when prompted.

## Manual Setup

If you prefer to set things up manually:

### Prerequisites

```bash
brew install node ffmpeg python3
brew install --cask hammerspoon
```

### Build

```bash
cd /path/to/ohmyvoice
npm ci && npm run build
```

### Python Backend

```bash
python3 -m venv contrib/sensevoice-backend/.venv
contrib/sensevoice-backend/.venv/bin/pip3 install -r contrib/sensevoice-backend/requirements.txt
bash contrib/sensevoice-backend/download_model.sh
```

The daemon starts the backend automatically when using the default bundled endpoint (`VOICE_BACKEND=managed`). If you set a custom `VOICE_ENDPOINT`, the daemon defaults to `external` mode — set `VOICE_BACKEND=managed` explicitly if you still want auto-management, or start `server.py` yourself.

### Configure Hammerspoon

Run the installer or copy manually:

```bash
bash contrib/macos/install.sh
# or: cp contrib/macos/ohmyvoice.lua ~/.hammerspoon/init.lua
```

If copying manually, edit `~/.hammerspoon/init.lua`:

1. Set `projectDir` to your ohmyvoice checkout path.
2. Adjust optional env vars as needed (model, audio device, sounds).

Reload: menubar Hammerspoon icon → **Reload Config**.

## Why Hammerspoon manages the daemon

macOS LaunchAgents run in a restricted session context. ffmpeg's AVFoundation audio capture requires a full AudioSession (tied to the window server) to function correctly. Without it, audio is captured at ~1/10 the expected bitrate, producing sped-up, noisy recordings.

Hammerspoon is a GUI application with a window server connection. Processes it spawns inherit a proper AudioSession, so ffmpeg records normally.

## Hotkey

**Hold Right Command** to record, release to stop.

To change the key, edit the `keyCode` check in `ohmyvoice.lua`:

| Key           | keyCode |
| ------------- | ------- |
| Right Command | 54      |
| Left Command  | 55      |
| Right Option  | 61      |
| F1            | 122     |
| F5            | 96      |

For modifier keys (Command, Option), the eventtap listens to `flagsChanged`.
For function keys, switch to `keyDown`/`keyUp` events — see the git history for an F1 example.

## Audio device selection

Default is `:default` (system default input). If a virtual audio device (e.g. Oray/SunLogin) is installed and set as default, override explicitly:

```bash
# List devices
ffmpeg -f avfoundation -list_devices true -i ""

# Set in Hammerspoon env, e.g. device index 1 = MacBook microphone
VOICE_RECORD_ARGS = "-f avfoundation -i :1 -ac 1 -flush_packets 1 -y"
```

## Clipboard encoding

Set `LANG = "en_US.UTF-8"` in the daemon environment (already in the example config). Without it, `pbcopy` may corrupt non-ASCII text.

## Prompt sounds

Override via environment variables. Available system sounds: Basso, Blow, Bottle, Frog, Funk, Glass, Hero, Morse, Ping, Pop, Purr, Sosumi, Submarine, Tink.

```lua
VOICE_START_SOUND_ARGS = "-v 0.6 /System/Library/Sounds/Funk.aiff",
VOICE_STOP_SOUND_ARGS  = "-v 0.6 /System/Library/Sounds/Glass.aiff",
```

Volume range: `0.0` – `1.0`. Default is `0.35`.

## Verify

```bash
node dist/cli.js status
```

## Troubleshooting

- **No sound / sped-up audio**: Daemon must be launched from Hammerspoon, not LaunchAgent. Check audio device index.
- **Clipboard garbled**: Ensure `LANG=en_US.UTF-8` is set in daemon environment.
- **Hotkey not working**: Check Accessibility permission for Hammerspoon. Reload config after edits.
- **Microphone permission**: Run `./setup-macos.sh` (which triggers the prompt) or run the daemon once from an interactive terminal.
- **ffmpeg not found**: Ensure `PATH` includes `/opt/homebrew/bin` in the daemon environment.
