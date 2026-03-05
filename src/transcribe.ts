import { readFile } from "node:fs/promises";

import type { AppConfig } from "./config.js";

export async function transcribeFile(filePath: string, config: AppConfig): Promise<string> {
  const audioData = await readFile(filePath);
  const payload = buildPayload(audioData, config);

  const abortController = new AbortController();
  const timeout = setTimeout(() => {
    abortController.abort();
  }, config.requestTimeoutMs);

  try {
    const response = await fetch(config.endpoint, {
      method: "POST",
      headers: buildHeaders(config),
      body: JSON.stringify(payload),
      signal: abortController.signal
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Backend returned ${response.status}: ${truncate(body, 400)}`);
    }

    const responsePayload: unknown = await response.json();
    const text = extractCompletionText(responsePayload);
    if (!text) {
      throw new Error("Backend returned empty transcript");
    }

    return text;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`Transcription timed out after ${config.requestTimeoutMs}ms`);
    }

    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function buildHeaders(config: AppConfig): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };

  if (!config.apiKey) {
    return headers;
  }

  headers.Authorization = `Bearer ${config.apiKey}`;
  return headers;
}

function buildPayload(audioData: Buffer, config: AppConfig): Record<string, unknown> {
  const audioDataUrl = `data:audio/wav;base64,${audioData.toString("base64")}`;
  const prompt = buildPrompt(config.prompt, config.language);

  return {
    model: config.model,
    messages: [
      {
        role: "user",
        content: [
          {
            type: "audio_url",
            audio_url: {
              url: audioDataUrl
            }
          },
          {
            type: "text",
            text: prompt
          }
        ]
      }
    ],
    temperature: 0,
    max_tokens: config.maxTokens
  };
}

function buildPrompt(basePrompt: string, language: string | undefined): string {
  if (!language) {
    return basePrompt;
  }

  return `${basePrompt} Use language: ${language}.`;
}

function extractCompletionText(payload: unknown): string | null {
  const choices = getObjectValue(payload, "choices");
  if (!Array.isArray(choices) || choices.length === 0) {
    return null;
  }

  const firstChoice = choices[0];
  const message = getObjectValue(firstChoice, "message");
  const content = getObjectValue(message, "content");
  const normalized = normalizeOpenAiContent(content);
  if (!normalized) {
    return null;
  }

  const parsedAsJson = parseJsonText(normalized);
  if (parsedAsJson) {
    const textValue = getObjectValue(parsedAsJson, "text");
    if (typeof textValue === "string" && textValue.trim().length > 0) {
      return normalizeTranscriptText(textValue);
    }
  }

  return normalizeTranscriptText(normalized);
}

function getObjectValue(value: unknown, key: string): unknown {
  if (typeof value !== "object" || value === null) {
    return undefined;
  }

  return (value as Record<string, unknown>)[key];
}

function normalizeOpenAiContent(content: unknown): string | null {
  if (typeof content === "string") {
    const text = stripCodeFence(content).trim();
    return text.length > 0 ? text : null;
  }

  if (!Array.isArray(content)) {
    return null;
  }

  const textParts = content
    .map((part) => {
      if (typeof part !== "object" || part === null) {
        return "";
      }

      const partType = (part as Record<string, unknown>).type;
      if (partType !== "text") {
        return "";
      }

      const text = (part as Record<string, unknown>).text;
      return typeof text === "string" ? text : "";
    })
    .filter((text) => text.trim().length > 0);

  if (textParts.length === 0) {
    return null;
  }

  return stripCodeFence(textParts.join("\n")).trim();
}

function parseJsonText(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
    return null;
  }

  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return null;
    }

    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

function stripCodeFence(text: string): string {
  const match = text.match(/^```(?:json|text)?\s*([\s\S]*?)\s*```$/i);
  if (!match || !match[1]) {
    return text;
  }

  return match[1];
}

function normalizeTranscriptText(text: string): string | null {
  const normalized = text
    .trim()
    .replace(/^language\s+[^\r\n<]+<asr_text>\s*/i, "")
    .replace(/^<asr_text>\s*/i, "")
    .trim();

  if (normalized.length === 0) {
    return null;
  }

  return normalized;
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength)}...`;
}
