import { spawn } from "node:child_process";

const WAYLAND_CLIPBOARD_COMMAND = "wl-copy";
const BACKGROUND_COMMAND_GRACE_MS = 300;

export async function copyToClipboard(command: string, text: string): Promise<void> {
  const args: string[] = [];
  await runCommand(command, args, text, { waitForExit: false });
}

export async function sendNotification(
  command: string,
  title: string,
  body: string
): Promise<void> {
  await runCommand(command, [title, body]);
}

export async function playSound(command: string, args: string[]): Promise<void> {
  await runCommand(command, args);
}

interface RunCommandOptions {
  waitForExit?: boolean;
  backgroundGraceMs?: number;
}

async function runCommand(
  command: string,
  args: string[],
  input?: string,
  options: RunCommandOptions = {}
): Promise<void> {
  const waitForExit = options.waitForExit ?? true;
  const backgroundGraceMs = options.backgroundGraceMs ?? BACKGROUND_COMMAND_GRACE_MS;

  await new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: ["pipe", "ignore", "pipe"]
    });

    let stderr = "";

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.once("error", (error) => {
      reject(new Error(`Failed to start ${command}: ${error.message}`));
    });

    let settled = false;
    let backgroundTimer: NodeJS.Timeout | null = null;

    const settle = (handler: () => void): void => {
      if (settled) {
        return;
      }

      if (backgroundTimer) {
        clearTimeout(backgroundTimer);
        backgroundTimer = null;
      }

      settled = true;
      handler();
    };

    const onClose = (code: number | null): void => {
      if (code === 0) {
        settle(resolve);
        return;
      }

      settle(() => reject(buildCommandExitError(command, code, stderr)));
    };

    child.once("close", onClose);

    if (input !== undefined) {
      child.stdin.write(input);
    }

    child.stdin.end();

    if (!waitForExit) {
      backgroundTimer = setTimeout(() => {
        settle(resolve);
      }, backgroundGraceMs);
    }
  });
}

function buildCommandExitError(command: string, code: number | null, stderr: string): Error {
  const trimmedStderr = stderr.trim();
  const extra = trimmedStderr.length > 0 ? `: ${trimmedStderr}` : "";
  let message = `${command} exited with code ${String(code)}${extra}`;

  if (
    command === WAYLAND_CLIPBOARD_COMMAND &&
    trimmedStderr.includes("Failed to connect to a Wayland server")
  ) {
    message +=
      ". wl-copy requires an active Wayland session; start omarvoice.service from graphical-session.target or set VOICE_CLIPBOARD_COMMAND to a clipboard tool that matches the current session.";
  }

  return new Error(message);
}
