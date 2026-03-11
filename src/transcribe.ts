import { readFile } from "node:fs/promises";

import type { AppConfig } from "./config.js";

const MAX_TRANSCRIBE_ATTEMPTS = 2;
const FILLER_WORD_BOUNDARY = "\\s,，.。!?！？、;；:：";
const CHINESE_DIGIT_MAP: Record<string, string> = {
  零: "0",
  〇: "0",
  一: "1",
  幺: "1",
  二: "2",
  两: "2",
  三: "3",
  四: "4",
  五: "5",
  六: "6",
  七: "7",
  八: "8",
  九: "9"
};
const CHINESE_SMALL_UNIT_MAP: Record<string, number> = {
  十: 10,
  百: 100,
  千: 1000
};
const CHINESE_LARGE_UNIT_MAP: Record<string, number> = {
  万: 10_000,
  亿: 100_000_000
};
const CHINESE_INTEGER_PATTERN = /^[零〇一二两三四五六七八九十百千万亿]+$/;
const CHINESE_DIGIT_SEQUENCE_PATTERN = /^[零〇一二两三四五六七八九幺]+$/;
const CHINESE_DIGIT_SEQUENCE_GLOBAL_PATTERN = /[零〇一二两三四五六七八九幺]{3,}/g;
const VERSION_PATTERN =
  /版本\s*([零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二两三四五六七八九十百千万亿]+)+)/g;
const PERCENTAGE_PATTERN =
  /百分之([零〇一二两三四五六七八九十百千万亿点]+)(?![零〇一二两三四五六七八九十百千万亿点])/g;
const DECIMAL_PATTERN =
  /([零〇一二两三四五六七八九十百千万亿]+)点([零〇一二两三四五六七八九]{1,6})/g;
const DECIMAL_TIME_PREFIXES = [
  "上午",
  "下午",
  "晚上",
  "凌晨",
  "早上",
  "中午",
  "傍晚",
  "今晚",
  "今早",
  "明早",
  "夜里",
  "星期",
  "礼拜"
];
const DECIMAL_TIME_SUFFIX_CHARS = new Set(["分", "秒", "整", "半", "刻", "钟", "鐘"]);
const STANDALONE_E_PATTERN = new RegExp(
  `(^|[${FILLER_WORD_BOUNDARY}])(?:恶)+(?=($|[${FILLER_WORD_BOUNDARY}]))`,
  "g"
);
const COMPUTING_TERM_NORMALIZERS: Array<{ pattern: RegExp; replacement: string }> = [
  { pattern: /\bmac\s*os\b/gi, replacement: "macOS" },
  { pattern: /\bubuntu\b/gi, replacement: "Ubuntu" },
  { pattern: /\bwindows\b/gi, replacement: "Windows" },
  { pattern: /\blinux\b/gi, replacement: "Linux" },
  { pattern: /\bgithub\b/gi, replacement: "GitHub" },
  { pattern: /\bapi\b/gi, replacement: "API" },
  { pattern: /\bcli\b/gi, replacement: "CLI" },
  { pattern: /\bssh\b/gi, replacement: "SSH" },
  { pattern: /\bdocker\b/gi, replacement: "Docker" },
  { pattern: /\bmac\b/gi, replacement: "mac" },
  { pattern: /\bgit\b/gi, replacement: "git" },
  { pattern: /乌班图/g, replacement: "Ubuntu" }
];

type TranscribeErrorCode = "timeout" | "emptyTranscript" | "backend" | "unknown";

class TranscribeError extends Error {
  public constructor(
    message: string,
    public readonly code: TranscribeErrorCode = "unknown"
  ) {
    super(message);
    this.name = "TranscribeError";
  }
}

export async function transcribeFile(filePath: string, config: AppConfig): Promise<string> {
  const audioData = await readFile(filePath);
  const payload = buildPayload(audioData, config);
  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= MAX_TRANSCRIBE_ATTEMPTS; attempt += 1) {
    try {
      return await submitTranscriptionRequest(payload, config);
    } catch (error) {
      const normalizedError = normalizeError(error);
      lastError = normalizedError;

      if (attempt < MAX_TRANSCRIBE_ATTEMPTS && isRetryableTranscriptionError(normalizedError)) {
        continue;
      }

      throw normalizedError;
    }
  }

  throw lastError ?? new Error("Transcription failed");
}

async function submitTranscriptionRequest(
  payload: Record<string, unknown>,
  config: AppConfig
): Promise<string> {
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
      throw new TranscribeError(
        `Backend returned ${response.status}: ${truncate(body, 400)}`,
        "backend"
      );
    }

    const responsePayload: unknown = await response.json();
    const text = extractCompletionText(responsePayload);
    if (!text) {
      throw new TranscribeError("Backend returned empty transcript", "emptyTranscript");
    }

    return text;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new TranscribeError(
        `Transcription timed out after ${config.requestTimeoutMs}ms`,
        "timeout"
      );
    }

    throw normalizeError(error);
  } finally {
    clearTimeout(timeout);
  }
}

function normalizeError(error: unknown): Error {
  if (error instanceof Error) {
    return error;
  }

  return new Error(String(error));
}

function isRetryableTranscriptionError(error: Error): boolean {
  if (!(error instanceof TranscribeError)) {
    return false;
  }

  return error.code === "timeout" || error.code === "emptyTranscript";
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

  const sanitized = sanitizeTranscriptText(normalized);
  if (sanitized.length === 0) {
    return null;
  }

  const numericNormalized = normalizeNumericText(sanitized);
  const termNormalized = normalizeComputingTerms(
    numericNormalized.length > 0 ? numericNormalized : sanitized
  );
  return termNormalized.length > 0 ? termNormalized : null;
}

function sanitizeTranscriptText(text: string): string {
  return text
    .replace(/呃+/g, "")
    .replace(STANDALONE_E_PATTERN, "$1")
    .replace(/[，,、;；:：]\s*[，,、;；:：]+/g, "，")
    .replace(/^[，,。.!?！？、;；:：\s]+/g, "")
    .replace(/[，,、;；:：\s]+$/g, "")
    .replace(/(?:！|!)+/g, (match) => (match.includes("！") ? "。" : "."))
    .replace(/((?:。|\.(?!\d)|[!?！？]))\s*[，,、;；:：]+/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function normalizeNumericText(text: string): string {
  return normalizeDigitSequences(
    normalizeStandaloneDecimals(normalizePercentages(normalizeVersions(text)))
  );
}

function normalizeVersions(text: string): string {
  return text.replace(VERSION_PATTERN, (match, rawVersion) => {
    const normalizedVersion = parseChineseVersion(rawVersion);
    if (!normalizedVersion) {
      return match;
    }

    return `版本 ${normalizedVersion}`;
  });
}

function normalizePercentages(text: string): string {
  return text.replace(PERCENTAGE_PATTERN, (match, rawNumber) => {
    const normalizedNumber = parseChineseNumber(rawNumber);
    if (!normalizedNumber) {
      return match;
    }

    return `${normalizedNumber}%`;
  });
}

function normalizeStandaloneDecimals(text: string): string {
  return text.replace(DECIMAL_PATTERN, (match, rawInteger, rawFraction, offset, source) => {
    if (shouldKeepAsTime(source, offset, match.length)) {
      return match;
    }

    const integerPart = parseChineseInteger(rawInteger);
    const fractionPart = parseChineseDigitSequence(rawFraction);
    if (!integerPart || !fractionPart) {
      return match;
    }

    return `${integerPart}.${fractionPart}`;
  });
}

function normalizeDigitSequences(text: string): string {
  return text.replace(CHINESE_DIGIT_SEQUENCE_GLOBAL_PATTERN, (match, offset, source) => {
    if (!isStandaloneDigitSequence(source, offset, match.length)) {
      return match;
    }

    return parseChineseDigitSequence(match) ?? match;
  });
}

function isStandaloneDigitSequence(text: string, offset: number, length: number): boolean {
  const previousChar = text.at(offset - 1);
  const nextChar = text.at(offset + length);
  return (
    !isChineseNumericContext(previousChar) &&
    !isChineseNumericContext(nextChar) &&
    previousChar !== "." &&
    nextChar !== "."
  );
}

function isChineseNumericContext(char: string | undefined): boolean {
  return char !== undefined && /[零〇一二两三四五六七八九幺十百千万亿点]/.test(char);
}

function normalizeComputingTerms(text: string): string {
  return COMPUTING_TERM_NORMALIZERS.reduce(
    (currentText, { pattern, replacement }) => currentText.replace(pattern, replacement),
    text
  );
}

function shouldKeepAsTime(text: string, offset: number, matchLength: number): boolean {
  const preceding = text.slice(Math.max(0, offset - 2), offset);
  if (preceding === "周") {
    return true;
  }

  if (DECIMAL_TIME_PREFIXES.some((prefix) => preceding.endsWith(prefix))) {
    return true;
  }

  const nextChar = text.at(offset + matchLength);
  return nextChar ? DECIMAL_TIME_SUFFIX_CHARS.has(nextChar) : false;
}

function parseChineseVersion(value: string): string | null {
  const segments = value.split("点");
  if (segments.length < 2) {
    return null;
  }

  const normalizedSegments = segments.map((segment) => parseChineseInteger(segment));
  return normalizedSegments.every((segment) => Boolean(segment))
    ? normalizedSegments.join(".")
    : null;
}

function parseChineseNumber(value: string): string | null {
  if (value.includes("点")) {
    const parts = value.split("点");
    if (parts.length !== 2) {
      return null;
    }

    const [integerSource, fractionSource] = parts;
    if (integerSource === undefined || fractionSource === undefined) {
      return null;
    }

    const integerPart = parseChineseInteger(integerSource);
    const fractionPart = parseChineseDigitSequence(fractionSource);
    if (!integerPart || !fractionPart) {
      return null;
    }

    return `${integerPart}.${fractionPart}`;
  }

  return parseChineseInteger(value);
}

function parseChineseInteger(value: string): string | null {
  if (!CHINESE_INTEGER_PATTERN.test(value)) {
    return null;
  }

  if (CHINESE_DIGIT_SEQUENCE_PATTERN.test(value)) {
    return String(Number.parseInt(parseChineseDigitSequence(value) ?? "", 10));
  }

  let total = 0;
  let section = 0;
  let currentDigit = 0;

  for (const char of value) {
    const digitValue = CHINESE_DIGIT_MAP[char];
    if (digitValue !== undefined) {
      currentDigit = Number.parseInt(digitValue, 10);
      continue;
    }

    const smallUnit = CHINESE_SMALL_UNIT_MAP[char];
    if (smallUnit !== undefined) {
      section += (currentDigit || 1) * smallUnit;
      currentDigit = 0;
      continue;
    }

    const largeUnit = CHINESE_LARGE_UNIT_MAP[char];
    if (largeUnit !== undefined) {
      section += currentDigit;
      total += (section || 1) * largeUnit;
      section = 0;
      currentDigit = 0;
      continue;
    }

    return null;
  }

  return String(total + section + currentDigit);
}

function parseChineseDigitSequence(value: string): string | null {
  if (!CHINESE_DIGIT_SEQUENCE_PATTERN.test(value)) {
    return null;
  }

  return value
    .split("")
    .map((char) => CHINESE_DIGIT_MAP[char] ?? "")
    .join("");
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength)}...`;
}
