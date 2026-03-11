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

const DEFAULT_RECORD_ARGS = ["--rate", "16000", "--channels", "1"];
const DEFAULT_SOUND_VOLUME = "0.35";
const DEFAULT_START_SOUND_ARGS = [
  "--volume",
  DEFAULT_SOUND_VOLUME,
  "/usr/share/sounds/freedesktop/stereo/bell.oga"
];
const DEFAULT_STOP_SOUND_ARGS = [
  "--volume",
  DEFAULT_SOUND_VOLUME,
  "/usr/share/sounds/freedesktop/stereo/complete.oga"
];

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const runtimeDir = env.XDG_RUNTIME_DIR ?? "/tmp";

  return {
    socketPath: env.VOICE_SOCKET_PATH ?? join(runtimeDir, "omarvoice.sock"),
    endpoint: env.VOICE_ENDPOINT ?? "http://127.0.0.1:8000/v1/chat/completions",
    apiKey: normalizeOptional(env.VOICE_API_KEY),
    tmpDir: env.VOICE_TMP_DIR ?? "/tmp",
    recordCommand: env.VOICE_RECORD_COMMAND ?? "pw-record",
    recordArgs: parseArgs(env.VOICE_RECORD_ARGS) ?? DEFAULT_RECORD_ARGS,
    startSoundCommand: env.VOICE_START_SOUND_COMMAND ?? "pw-play",
    startSoundArgs: parseArgs(env.VOICE_START_SOUND_ARGS) ?? DEFAULT_START_SOUND_ARGS,
    stopSoundCommand: env.VOICE_STOP_SOUND_COMMAND ?? "pw-play",
    stopSoundArgs: parseArgs(env.VOICE_STOP_SOUND_ARGS) ?? DEFAULT_STOP_SOUND_ARGS,
    clipboardCommand: env.VOICE_CLIPBOARD_COMMAND ?? "wl-copy",
    notifyCommand: env.VOICE_NOTIFY_COMMAND ?? "notify-send",
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
