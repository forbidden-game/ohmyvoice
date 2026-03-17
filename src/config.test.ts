import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { loadConfig } from "./config.js";

describe("loadConfig sound defaults", () => {
  it("uses the tighter default transcription prompt", () => {
    const config = loadConfig({});

    assert.equal(
      config.prompt,
      "Please transcribe the audio and return plain text only. Keep common computing terms in English. Use Arabic numerals for numbers, decimals, times, dates, versions, percentages, and digit sequences. Do not write numbers in Chinese characters."
    );
  });

  it("uses a lower default volume for start and stop sounds", () => {
    const config = loadConfig({}, "linux");

    assert.deepEqual(config.startSoundArgs, [
      "--volume",
      "0.35",
      "/usr/share/sounds/freedesktop/stereo/bell.oga"
    ]);
    assert.deepEqual(config.stopSoundArgs, [
      "--volume",
      "0.35",
      "/usr/share/sounds/freedesktop/stereo/complete.oga"
    ]);
  });

  it("still allows overriding sound args from env", () => {
    const config = loadConfig({
      VOICE_START_SOUND_ARGS: "--volume 0.2 /tmp/start.oga",
      VOICE_STOP_SOUND_ARGS: "--volume 0.1 /tmp/stop.oga"
    });

    assert.deepEqual(config.startSoundArgs, ["--volume", "0.2", "/tmp/start.oga"]);
    assert.deepEqual(config.stopSoundArgs, ["--volume", "0.1", "/tmp/stop.oga"]);
  });
});

describe("loadConfig macOS defaults", () => {
  it("returns macOS defaults when platform is darwin", () => {
    const config = loadConfig({}, "darwin");

    assert.equal(config.recordCommand, "ffmpeg");
    assert.deepEqual(config.recordArgs, [
      "-f",
      "avfoundation",
      "-i",
      ":default",
      "-ar",
      "16000",
      "-ac",
      "1",
      "-c:a",
      "libopus",
      "-application",
      "voip",
      "-flush_packets",
      "1",
      "-y"
    ]);
    assert.equal(config.recordFileExtension, ".ogg");
    assert.equal(config.startSoundCommand, "afplay");
    assert.deepEqual(config.startSoundArgs, ["-v", "0.35", "/System/Library/Sounds/Tink.aiff"]);
    assert.equal(config.stopSoundCommand, "afplay");
    assert.deepEqual(config.stopSoundArgs, ["-v", "0.35", "/System/Library/Sounds/Glass.aiff"]);
    assert.equal(config.clipboardCommand, "pbcopy");
    assert.equal(config.notifyCommand, "osascript");
    assert.equal(config.socketPath, "/tmp/ohmyvoice.sock");
  });

  it("returns Linux defaults when platform is linux", () => {
    const config = loadConfig({}, "linux");

    assert.equal(config.recordCommand, "pw-record");
    assert.deepEqual(config.recordArgs, ["--rate", "16000", "--channels", "1"]);
    assert.equal(config.recordFileExtension, ".wav");
    assert.equal(config.startSoundCommand, "pw-play");
    assert.equal(config.stopSoundCommand, "pw-play");
    assert.equal(config.clipboardCommand, "wl-copy");
    assert.equal(config.notifyCommand, "notify-send");
  });

  it("env var overrides take precedence regardless of platform", () => {
    const config = loadConfig(
      { VOICE_RECORD_COMMAND: "custom-recorder", VOICE_CLIPBOARD_COMMAND: "xclip" },
      "darwin"
    );

    assert.equal(config.recordCommand, "custom-recorder");
    assert.equal(config.clipboardCommand, "xclip");
  });
});

describe("loadConfig backendMode", () => {
  it("defaults to managed on macOS with default endpoint", () => {
    const config = loadConfig({}, "darwin");
    assert.equal(config.backendMode, "managed");
  });

  it("defaults to external on Linux even with default endpoint", () => {
    const config = loadConfig({}, "linux");
    assert.equal(config.backendMode, "external");
  });

  it("defaults to external on macOS when endpoint port differs", () => {
    const config = loadConfig(
      { VOICE_ENDPOINT: "http://127.0.0.1:8787/v1/chat/completions" },
      "darwin"
    );
    assert.equal(config.backendMode, "external");
  });

  it("defaults to external on macOS with SSH tunnel endpoint", () => {
    const config = loadConfig(
      { VOICE_ENDPOINT: "http://127.0.0.1:18000/v1/chat/completions" },
      "darwin"
    );
    assert.equal(config.backendMode, "external");
  });

  it("defaults to external on macOS with localhost endpoint", () => {
    const config = loadConfig(
      { VOICE_ENDPOINT: "http://localhost:8000/v1/chat/completions" },
      "darwin"
    );
    assert.equal(config.backendMode, "external");
  });

  it("defaults to external on macOS with custom local path", () => {
    const config = loadConfig({ VOICE_ENDPOINT: "http://127.0.0.1:8000/mock-server" }, "darwin");
    assert.equal(config.backendMode, "external");
  });

  it("defaults to external on macOS with remote endpoint", () => {
    const config = loadConfig(
      { VOICE_ENDPOINT: "https://api.example.com/v1/chat/completions" },
      "darwin"
    );
    assert.equal(config.backendMode, "external");
  });

  it("defaults to external on macOS with IPv6 localhost endpoint", () => {
    const config = loadConfig(
      { VOICE_ENDPOINT: "http://[::1]:8000/v1/chat/completions" },
      "darwin"
    );
    assert.equal(config.backendMode, "external");
  });

  it("explicit VOICE_BACKEND=managed overrides any endpoint", () => {
    const config = loadConfig(
      {
        VOICE_BACKEND: "managed",
        VOICE_ENDPOINT: "https://api.example.com/v1/chat/completions"
      },
      "darwin"
    );
    assert.equal(config.backendMode, "managed");
  });

  it("explicit VOICE_BACKEND=external overrides default endpoint on macOS", () => {
    const config = loadConfig({ VOICE_BACKEND: "external" }, "darwin");
    assert.equal(config.backendMode, "external");
  });
});
