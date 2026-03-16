import { join } from "node:path";

export interface AppConfig {
  socketPath: string;
  endpoint: string;
  apiKey: string | undefined;
  tmpDir: string;
  recordCommand: string;
  recordArgs: string[];
  startSoundCommand: string;
  startSoundArgs: string[];
  stopSoundCommand: string;
  stopSoundArgs: string[];
  clipboardCommand: string;
  notifyCommand: string;
  model: string;
  prompt: string;
  language: string | undefined;
  maxTokens: number;
  requestTimeoutMs: number;
}

const DEFAULT_SOUND_VOLUME = "0.35";

const LINUX_RECORD_ARGS = ["--rate", "16000", "--channels", "1"];
const LINUX_START_SOUND_ARGS = [
  "--volume",
  DEFAULT_SOUND_VOLUME,
  "/usr/share/sounds/freedesktop/stereo/bell.oga"
];
const LINUX_STOP_SOUND_ARGS = [
  "--volume",
  DEFAULT_SOUND_VOLUME,
  "/usr/share/sounds/freedesktop/stereo/complete.oga"
];

const MACOS_RECORD_ARGS = [
  "-f",
  "avfoundation",
  "-i",
  ":default",
  "-ar",
  "16000",
  "-ac",
  "1",
  "-y"
];
const MACOS_START_SOUND_ARGS = ["-v", DEFAULT_SOUND_VOLUME, "/System/Library/Sounds/Tink.aiff"];
const MACOS_STOP_SOUND_ARGS = ["-v", DEFAULT_SOUND_VOLUME, "/System/Library/Sounds/Glass.aiff"];

export function loadConfig(
  env: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform
): AppConfig {
  const isDarwin = platform === "darwin";
  const runtimeDir = env.XDG_RUNTIME_DIR ?? "/tmp";
  const defaultSocketPath = isDarwin ? "/tmp/omarvoice.sock" : join(runtimeDir, "omarvoice.sock");

  return {
    socketPath: env.VOICE_SOCKET_PATH ?? defaultSocketPath,
    endpoint: env.VOICE_ENDPOINT ?? "http://127.0.0.1:8000/v1/chat/completions",
    apiKey: normalizeOptional(env.VOICE_API_KEY),
    tmpDir: env.VOICE_TMP_DIR ?? "/tmp",
    recordCommand: env.VOICE_RECORD_COMMAND ?? (isDarwin ? "ffmpeg" : "pw-record"),
    recordArgs:
      parseArgs(env.VOICE_RECORD_ARGS) ?? (isDarwin ? MACOS_RECORD_ARGS : LINUX_RECORD_ARGS),
    startSoundCommand: env.VOICE_START_SOUND_COMMAND ?? (isDarwin ? "afplay" : "pw-play"),
    startSoundArgs:
      parseArgs(env.VOICE_START_SOUND_ARGS) ??
      (isDarwin ? MACOS_START_SOUND_ARGS : LINUX_START_SOUND_ARGS),
    stopSoundCommand: env.VOICE_STOP_SOUND_COMMAND ?? (isDarwin ? "afplay" : "pw-play"),
    stopSoundArgs:
      parseArgs(env.VOICE_STOP_SOUND_ARGS) ??
      (isDarwin ? MACOS_STOP_SOUND_ARGS : LINUX_STOP_SOUND_ARGS),
    clipboardCommand: env.VOICE_CLIPBOARD_COMMAND ?? (isDarwin ? "pbcopy" : "wl-copy"),
    notifyCommand: env.VOICE_NOTIFY_COMMAND ?? (isDarwin ? "osascript" : "notify-send"),
    model: normalizeOptional(env.VOICE_MODEL) ?? "Qwen/Qwen3-ASR-1.7B",
    prompt:
      normalizeOptional(env.VOICE_PROMPT) ??
      "Please transcribe the audio and return plain text only. Keep common computing terms in English. Use Arabic numerals for numbers, decimals, times, dates, versions, percentages, and digit sequences. Do not write numbers in Chinese characters.",
    language: normalizeOptional(env.VOICE_LANGUAGE),
    maxTokens: parsePositiveInt(env.VOICE_MAX_TOKENS, 1024),
    requestTimeoutMs: parsePositiveInt(env.VOICE_REQUEST_TIMEOUT_MS, 45_000)
  };
}

function normalizeOptional(value: string | undefined): string | undefined {
  if (value === undefined) {
    return undefined;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function parseArgs(raw: string | undefined): string[] | undefined {
  if (!raw || raw.trim().length === 0) {
    return undefined;
  }

  return raw
    .split(/\s+/)
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0);
}

function parsePositiveInt(raw: string | undefined, fallback: number): number {
  if (!raw) {
    return fallback;
  }

  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }

  return parsed;
}
