import { spawn, type ChildProcess } from "node:child_process";
import { mkdir, rm } from "node:fs/promises";
import { join } from "node:path";

import type { AppConfig } from "./config.js";
import type { VoiceAction, VoiceResponse } from "./ipc.js";
import { transitionState, type VoiceState } from "./state-machine.js";
import { copyToClipboard, playSound, sendNotification } from "./system.js";
import { transcribeFile } from "./transcribe.js";

/** Named export for module-level test coverage. */
export function isRecorderExitOk(
  code: number | null,
  signal: NodeJS.Signals | null,
  stopSignalSent: boolean
): boolean {
  return (
    code === 0 ||
    signal === "SIGINT" ||
    signal === "SIGTERM" ||
    (stopSignalSent && signal === null && (code === 1 || code === 255))
  );
}

export class VoiceService {
  private state: VoiceState = "idle";
  private recorder: ChildProcess | null = null;
  private recordingFilePath: string | null = null;
  private recorderStderr = "";
  private lastError: string | null = null;
  private lastText: string | null = null;

  public constructor(private readonly config: AppConfig) {}

  public async handleAction(action: VoiceAction): Promise<VoiceResponse> {
    switch (action) {
      case "start":
        return this.startRecording();
      case "stop":
        return this.stopAndSubmit();
      case "status":
        return this.status();
      default:
        return this.failure(`Unsupported action: ${String(action)}`);
    }
  }

  public async shutdown(): Promise<void> {
    if (this.recorder && this.state === "recording") {
      try {
        await this.stopRecorder(this.recorder);
      } catch {
        this.recorder.kill("SIGKILL");
      }
    }

    this.recorder = null;

    if (this.recordingFilePath) {
      await rm(this.recordingFilePath, { force: true });
      this.recordingFilePath = null;
    }

    this.state = "idle";
  }

  private async startRecording(): Promise<VoiceResponse> {
    if (this.state === "recording") {
      return this.failure("Already recording");
    }

    if (this.state === "submitting") {
      return this.failure("Busy: transcription in progress");
    }

    await mkdir(this.config.tmpDir, { recursive: true });

    const filename = `omarvoice-${Date.now()}.wav`;
    const filePath = join(this.config.tmpDir, filename);
    const useStdinStop = this.config.recordCommand === "ffmpeg";
    const recorder = spawn(this.config.recordCommand, [...this.config.recordArgs, filePath], {
      stdio: [useStdinStop ? "pipe" : "ignore", "ignore", "pipe"]
    });

    this.recorderStderr = "";

    recorder.stderr?.on("data", (chunk) => {
      this.recorderStderr += chunk.toString();
      if (this.recorderStderr.length > 4_000) {
        this.recorderStderr = this.recorderStderr.slice(-4_000);
      }
    });

    try {
      await this.waitForRecorderStartup(recorder);
    } catch (error) {
      await rm(filePath, { force: true }).catch(() => undefined);
      const message = error instanceof Error ? error.message : String(error);
      this.lastError = message;
      return this.failure(message);
    }

    this.attachRuntimeRecorderListeners(recorder);

    this.recorder = recorder;
    this.recordingFilePath = filePath;
    this.state = transitionState(this.state, "start");
    this.lastError = null;
    this.playStartSoundBestEffort();

    return {
      ok: true,
      message: "Recording started",
      state: this.state
    };
  }

  private async stopAndSubmit(): Promise<VoiceResponse> {
    if (this.state === "idle") {
      return this.failure("Not recording");
    }

    if (this.state === "submitting") {
      return this.failure("Already submitting");
    }

    if (!this.recorder || !this.recordingFilePath) {
      this.state = "idle";
      return this.failure("Recorder process is not available");
    }

    const recorder = this.recorder;
    const recordingFilePath = this.recordingFilePath;

    this.state = transitionState(this.state, "stop");

    try {
      await this.stopRecorder(recorder);
      this.recorder = null;
      this.playStopSoundBestEffort();

      const text = await transcribeFile(recordingFilePath, this.config);
      await copyToClipboard(this.config.clipboardCommand, text);
      await this.notifyBestEffort("Voice Input Ready", truncate(text, 160));

      this.lastText = text;
      this.lastError = null;
      this.state = transitionState(this.state, "submitSuccess");

      return {
        ok: true,
        message: "Transcription finished and copied to clipboard",
        state: this.state,
        text
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.lastError = errorMessage;
      this.state = transitionState(this.state, "submitFailure");
      await this.notifyBestEffort("Voice Input Failed", truncate(errorMessage, 160));

      return {
        ok: false,
        message: errorMessage,
        state: this.state,
        error: errorMessage
      };
    } finally {
      this.recorder = null;
      this.recordingFilePath = null;
      await rm(recordingFilePath, { force: true }).catch(() => undefined);
    }
  }

  private status(): VoiceResponse {
    if (this.lastError) {
      return {
        ok: true,
        message: `state=${this.state}; lastError=${this.lastError}`,
        state: this.state,
        error: this.lastError
      };
    }

    if (this.lastText) {
      return {
        ok: true,
        message: `state=${this.state}; lastText=${truncate(this.lastText, 80)}`,
        state: this.state,
        text: this.lastText
      };
    }

    return {
      ok: true,
      message: `state=${this.state}`,
      state: this.state
    };
  }

  private failure(message: string): VoiceResponse {
    return {
      ok: false,
      message,
      state: this.state,
      error: message
    };
  }

  private async stopRecorder(recorder: ChildProcess): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      if (recorder.exitCode !== null || recorder.signalCode !== null) {
        resolve();
        return;
      }

      let settled = false;
      let stopSignalSent = false;

      const softTimeout = setTimeout(() => {
        stopSignalSent = true;
        recorder.kill("SIGTERM");
      }, 1_000);

      const hardTimeout = setTimeout(() => {
        stopSignalSent = true;
        recorder.kill("SIGKILL");
        settleError(
          new Error(
            `Recorder did not stop in time. stderr: ${truncate(this.recorderStderr.trim(), 500)}`
          )
        );
      }, 3_500);

      const settleBase = (): boolean => {
        if (settled) {
          return false;
        }

        settled = true;
        clearTimeout(softTimeout);
        clearTimeout(hardTimeout);
        recorder.removeListener("exit", onExit);
        recorder.removeListener("error", onError);
        return true;
      };

      const settleOk = (): void => {
        if (!settleBase()) {
          return;
        }

        resolve();
      };

      const settleError = (error: Error): void => {
        if (!settleBase()) {
          return;
        }

        reject(error);
      };

      const onExit = (code: number | null, signal: NodeJS.Signals | null): void => {
        if (isRecorderExitOk(code, signal, stopSignalSent)) {
          settleOk();
          return;
        }

        settleError(
          new Error(
            `Recorder exited unexpectedly (code=${String(code)}, signal=${String(signal)}). stderr: ${truncate(this.recorderStderr.trim(), 500)}`
          )
        );
      };

      const onError = (error: Error): void => {
        settleError(error);
      };

      recorder.once("exit", onExit);
      recorder.once("error", onError);

      stopSignalSent = true;
      // For ffmpeg, send 'q' via stdin for graceful shutdown that flushes output.
      // For other recorders (pw-record), use SIGINT.
      if (recorder.stdin?.writable) {
        recorder.stdin.write("q");
        recorder.stdin.end();
      } else {
        const killOk = recorder.kill("SIGINT");
        if (!killOk && (recorder.exitCode !== null || recorder.signalCode !== null)) {
          settleOk();
        }
      }
    });
  }

  private async notifyBestEffort(title: string, body: string): Promise<void> {
    await sendNotification(this.config.notifyCommand, title, body).catch(() => undefined);
  }

  private playStartSoundBestEffort(): void {
    void playSound(this.config.startSoundCommand, this.config.startSoundArgs).catch(
      () => undefined
    );
  }

  private playStopSoundBestEffort(): void {
    void playSound(this.config.stopSoundCommand, this.config.stopSoundArgs).catch(() => undefined);
  }

  private attachRuntimeRecorderListeners(recorder: ChildProcess): void {
    recorder.once("error", (error) => {
      if (this.recorder !== recorder) {
        return;
      }

      this.recorder = null;
      this.recordingFilePath = null;
      this.state = "idle";
      this.lastError = `Recorder failed: ${error.message}`;
    });

    recorder.once("exit", (code, signal) => {
      if (this.recorder !== recorder) {
        return;
      }

      if (this.state === "recording") {
        this.recorder = null;
        this.recordingFilePath = null;
        this.state = "idle";
        this.lastError = `Recorder stopped unexpectedly (code=${String(code)}, signal=${String(signal)})`;
      }
    });
  }

  private async waitForRecorderStartup(recorder: ChildProcess): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      let settled = false;

      const timeout = setTimeout(() => {
        settleOk();
      }, 200);

      const settleBase = (): boolean => {
        if (settled) {
          return false;
        }

        settled = true;
        clearTimeout(timeout);
        recorder.removeListener("error", onError);
        recorder.removeListener("exit", onExit);
        return true;
      };

      const settleOk = (): void => {
        if (!settleBase()) {
          return;
        }

        resolve();
      };

      const settleError = (error: Error): void => {
        if (!settleBase()) {
          return;
        }

        reject(error);
      };

      const onError = (error: Error): void => {
        settleError(new Error(`Recorder failed to start: ${error.message}`));
      };

      const onExit = (code: number | null, signal: NodeJS.Signals | null): void => {
        settleError(
          new Error(
            `Recorder exited during startup (code=${String(code)}, signal=${String(signal)})`
          )
        );
      };

      recorder.once("error", onError);
      recorder.once("exit", onExit);
    });
  }
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength)}...`;
}
