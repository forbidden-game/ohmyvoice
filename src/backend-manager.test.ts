import assert from "node:assert/strict";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it } from "node:test";

import type { AppConfig } from "./config.js";
import { loadConfig } from "./config.js";
import { BackendManager } from "./backend-manager.js";

function makeConfig(overrides: Partial<AppConfig> = {}): AppConfig {
  return {
    ...loadConfig({}, "darwin"),
    backendPidFile: join(
      tmpdir(),
      `ohmyvoice-backend-test-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}.pid`
    ),
    notifyCommand: "true",
    ...overrides
  };
}

describe("BackendManager external mode", () => {
  it("logs a hint for localhost endpoints without changing the endpoint", async () => {
    const endpoint = "http://localhost:8787/v1/chat/completions";
    const config = makeConfig({ backendMode: "external", endpoint });
    const manager = new BackendManager(config);
    const logs: string[] = [];
    const originalLog = console.log;

    console.log = (...args: unknown[]) => {
      logs.push(args.map(String).join(" "));
    };

    try {
      await manager.start();
    } finally {
      console.log = originalLog;
    }

    assert.equal(config.endpoint, endpoint);
    assert.deepEqual(logs, [
      'backend-manager: backend mode is "external". Set VOICE_BACKEND=managed to auto-start the local SenseVoice backend on this port.'
    ]);
  });

  it("does not log a hint for IPv6 localhost endpoints", async () => {
    const config = makeConfig({
      backendMode: "external",
      endpoint: "http://[::1]:8000/v1/chat/completions"
    });
    const manager = new BackendManager(config);
    const logs: string[] = [];
    const originalLog = console.log;

    console.log = (...args: unknown[]) => {
      logs.push(args.map(String).join(" "));
    };

    try {
      await manager.start();
    } finally {
      console.log = originalLog;
    }

    assert.deepEqual(logs, []);
  });
});

describe("BackendManager managed mode", () => {
  it("moves to a free port when the configured port is occupied", async () => {
    const occupiedServer = createServer();

    await new Promise<void>((resolve, reject) => {
      occupiedServer.once("error", reject);
      occupiedServer.listen(0, "127.0.0.1", () => resolve());
    });

    const address = occupiedServer.address();
    if (address === null || typeof address === "string") {
      throw new Error("expected an IPv4 address from occupied test server");
    }
    const occupiedPort = address.port;

    const config = makeConfig({
      backendMode: "managed",
      endpoint: `http://127.0.0.1:${occupiedPort}/v1/chat/completions`
    });
    const manager = new BackendManager(config) as unknown as {
      start: () => Promise<void>;
      isHealthy: () => Promise<boolean>;
      spawnBackend: () => Promise<void>;
      waitForHealth: () => Promise<void>;
    };

    manager.isHealthy = async () => false;
    manager.spawnBackend = async () => undefined;
    manager.waitForHealth = async () => undefined;

    try {
      await manager.start();
    } finally {
      await new Promise<void>((resolve, reject) => {
        occupiedServer.close((error) => {
          if (error) {
            reject(error);
            return;
          }
          resolve();
        });
      });
    }

    const resolvedUrl = new URL(config.endpoint);
    const resolvedPort = Number.parseInt(resolvedUrl.port, 10);

    assert.equal(resolvedUrl.hostname, "127.0.0.1");
    assert.notEqual(resolvedPort, occupiedPort);
    assert.ok(resolvedPort > occupiedPort);
    assert.ok(resolvedPort <= occupiedPort + 20);
  });
});
