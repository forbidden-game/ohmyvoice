import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { isRecorderExitOk } from "./service.js";

describe("isRecorderExitOk", () => {
  it("accepts exit code 0", () => {
    assert.equal(isRecorderExitOk(0, null, false), true);
  });

  it("accepts SIGINT signal", () => {
    assert.equal(isRecorderExitOk(null, "SIGINT", false), true);
  });

  it("accepts SIGTERM signal", () => {
    assert.equal(isRecorderExitOk(null, "SIGTERM", false), true);
  });

  it("accepts ffmpeg's 255 exit when stopSignalSent is true", () => {
    assert.equal(isRecorderExitOk(255, null, true), true);
  });

  it("accepts pw-record's 1 exit when stopSignalSent is true", () => {
    assert.equal(isRecorderExitOk(1, null, true), true);
  });

  it("rejects unexpected crash (code 1, no stop signal)", () => {
    assert.equal(isRecorderExitOk(1, null, false), false);
  });

  it("rejects unexpected exit 255 without stop signal", () => {
    assert.equal(isRecorderExitOk(255, null, false), false);
  });

  it("rejects unexpected exit codes even after stop signal", () => {
    assert.equal(isRecorderExitOk(99, null, true), false);
  });
});
