import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it } from "node:test";

import { copyToClipboard } from "./system.js";

describe("copyToClipboard", () => {
  it("runs wl-copy in foreground mode so errors are observable", async () => {
    const workspace = await mkdtemp(join(tmpdir(), "omarvoice-system-"));
    const dataPath = join(workspace, "stdin.txt");
    const argsPath = join(workspace, "args.txt");
    const commandPath = join(workspace, "wl-copy");
    const originalPath = process.env.PATH;

    await writeFile(
      commandPath,
      `#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" > ${shellQuote(argsPath)}
cat > ${shellQuote(dataPath)}
`,
      { mode: 0o755 }
    );

    process.env.PATH = `${workspace}:${originalPath ?? ""}`;

    try {
      await copyToClipboard("wl-copy", "hello clipboard");

      assert.equal(await readFile(argsPath, "utf8"), "--foreground\n");
      assert.equal(await readFile(dataPath, "utf8"), "hello clipboard");
    } finally {
      process.env.PATH = originalPath;
      await rm(workspace, { recursive: true, force: true });
    }
  });

  it("adds a focused hint when wl-copy cannot reach Wayland", async () => {
    const workspace = await mkdtemp(join(tmpdir(), "omarvoice-system-"));
    const commandPath = join(workspace, "wl-copy");
    const originalPath = process.env.PATH;

    await writeFile(
      commandPath,
      `#!/usr/bin/env bash
set -euo pipefail
echo "Failed to connect to a Wayland server" >&2
exit 1
`,
      { mode: 0o755 }
    );

    process.env.PATH = `${workspace}:${originalPath ?? ""}`;

    try {
      await assert.rejects(
        () => copyToClipboard("wl-copy", "hello clipboard"),
        /wl-copy requires an active Wayland session/
      );
    } finally {
      process.env.PATH = originalPath;
      await rm(workspace, { recursive: true, force: true });
    }
  });
});

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", `'\\''`)}'`;
}
