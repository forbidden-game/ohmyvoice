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
      "-y"
    ]);
    assert.equal(config.startSoundCommand, "afplay");
    assert.deepEqual(config.startSoundArgs, ["-v", "0.35", "/System/Library/Sounds/Tink.aiff"]);
    assert.equal(config.stopSoundCommand, "afplay");
    assert.deepEqual(config.stopSoundArgs, ["-v", "0.35", "/System/Library/Sounds/Glass.aiff"]);
    assert.equal(config.clipboardCommand, "pbcopy");
    assert.equal(config.notifyCommand, "osascript");
    assert.equal(config.socketPath, "/tmp/omarvoice.sock");
  });

  it("returns Linux defaults when platform is linux", () => {
    const config = loadConfig({}, "linux");

    assert.equal(config.recordCommand, "pw-record");
    assert.deepEqual(config.recordArgs, ["--rate", "16000", "--channels", "1"]);
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
