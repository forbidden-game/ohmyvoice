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
    const config = loadConfig({});

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
