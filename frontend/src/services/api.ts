type MetaEnv = {
  DEV?: boolean;
  VITE_API_BASE_URL?: string;
  VITE_BACKEND_URL?: string;
};

const meta = import.meta as ImportMeta & { env?: MetaEnv };
const fallbackEnv = (globalThis as { __APP_ENV__?: MetaEnv }).__APP_ENV__ ?? {};
const env = meta.env ?? fallbackEnv;

const ENV_BACKEND_URL = env.VITE_API_BASE_URL || env.VITE_BACKEND_URL || "";
const API_BASE_URL = env.DEV ? "" : ENV_BACKEND_URL;
const SESSION_KEY = "voice_os_session_id";

export interface QuickAction {
  label: string;
  value: string;
}

function normalizeApiLanguage(language: string): "hi" | "en" {
  const value = (language || "").trim().toLowerCase();
  return value === "hi" ? "hi" : "en";
}

export interface BackendResponse {
  request_id?: string;
  session_id: string;
  response_text: string;
  voice_text?: string | null;
  field_name: string | null;
  validation_passed: boolean;
  validation_error: string | null;
  session_complete: boolean;
  tts_error?: string | null;
  mode?: "info" | "action" | "clarify";
  action?: string | null;
  steps_done?: number;
  steps_total?: number;
  completed_fields?: string[];
  scheme_details?: {
    title?: string;
    description?: string;
    next_step?: string;
  } | null;
  recommended_schemes?: string[];
  user_profile?: Record<string, string | null>;
  quick_actions?: QuickAction[];
  transcript?: string;
  audio_base64?: string | null;
}

export interface OcrResponse {
  session_id: string;
  response_text: string;
  field_name: string | null;
  validation_passed: boolean;
  validation_error: string | null;
  session_complete: boolean;
  ocr_data: {
    full_name: string | null;
    aadhaar_number: string | null;
    date_of_birth: string | null;
    address: string | null;
    confidence: number;
  };
}

export interface TtsResponse {
  response_text: string;
  audio_base64: string;
}

export interface VoiceStateResponse {
  session_id: string;
  state: "idle" | "listening" | "processing" | "speaking" | "interrupted";
  interrupted: boolean;
}

export type ProcessTextStreamEvent =
  | { type: "meta"; payload: BackendResponse }
  | { type: "audio_chunk"; seq: number; text_segment: string; audio_base64: string }
  | { type: "interrupted"; session_id: string }
  | { type: "done"; session_id: string };

export interface StreamOptions {
  signal?: AbortSignal;
  maxBufferBytes?: number;
  retryAttempts?: number;
  retryDelayMs?: number;
}

const DEFAULT_STREAM_BUFFER_BYTES = 1024 * 1024;
const DEFAULT_STREAM_RETRY_ATTEMPTS = 2;
const DEFAULT_STREAM_RETRY_DELAY_MS = 300;

export function getOrCreateSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function clearSessionId(): void {
  localStorage.removeItem(SESSION_KEY);
}

async function postForm<T>(path: string, formData: FormData, language?: "hi" | "en"): Promise<T> {
  const requestHeaders: HeadersInit = {};
  if (language) {
    requestHeaders["x-language"] = language;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: requestHeaders,
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  const payload = (await response.json()) as T;
  const requestId = response.headers.get("x-request-id") || undefined;
  if (requestId && payload && typeof payload === "object" && !Array.isArray(payload)) {
    (payload as Record<string, unknown>).request_id =
      (payload as Record<string, unknown>).request_id || requestId;
  }

  return payload;
}

export async function processText(text: string, language: string): Promise<BackendResponse> {
  const sessionId = getOrCreateSessionId();
  const lang = normalizeApiLanguage(localStorage.getItem("language") || language || "en");
  const formData = new FormData();
  formData.append("text", text);
  formData.append("session_id", sessionId);
  formData.append("language", lang);
  return postForm<BackendResponse>("/api/process-text", formData, lang);
}

export async function processTextStream(
  text: string,
  language: string,
  onEvent: (event: ProcessTextStreamEvent) => void,
  onRequestId?: (requestId: string) => void,
  options?: StreamOptions,
): Promise<void> {
  const sessionId = getOrCreateSessionId();
  const lang = normalizeApiLanguage(localStorage.getItem("language") || language || "en");
  const formData = new FormData();
  formData.append("text", text);
  formData.append("session_id", sessionId);
  formData.append("language", lang);
  const retryAttempts = options?.retryAttempts ?? DEFAULT_STREAM_RETRY_ATTEMPTS;
  const retryDelayMs = options?.retryDelayMs ?? DEFAULT_STREAM_RETRY_DELAY_MS;
  const maxBufferBytes = options?.maxBufferBytes ?? DEFAULT_STREAM_BUFFER_BYTES;

  for (let attempt = 1; attempt <= retryAttempts; attempt += 1) {
    if (options?.signal?.aborted) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/process-text-stream`, {
        method: "POST",
        headers: { "x-language": lang },
        body: formData,
        signal: options?.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`Streaming request failed: ${response.status}`);
      }

      const requestId = response.headers.get("x-request-id");
      if (requestId && onRequestId) {
        onRequestId(requestId);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        if (buffer.length > maxBufferBytes) {
          if (import.meta.env.DEV) {
            console.warn("[stream] buffer overflow, clearing");
          }
          buffer = "";
        }

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            continue;
          }
          try {
            const parsed = JSON.parse(trimmed) as ProcessTextStreamEvent;
            try {
              onEvent(parsed);
            } catch (error) {
              if (import.meta.env.DEV) {
                console.warn("[stream] event handler failed", error);
              }
            }
          } catch (error) {
            if (import.meta.env.DEV) {
              console.warn("[stream] failed to parse event line", error);
            }
          }
        }
      }

      buffer += decoder.decode();
      const final = buffer.trim();
      if (final) {
        try {
          const parsed = JSON.parse(final) as ProcessTextStreamEvent;
          try {
            onEvent(parsed);
          } catch (error) {
            if (import.meta.env.DEV) {
              console.warn("[stream] event handler failed", error);
            }
          }
        } catch (error) {
          if (import.meta.env.DEV) {
            console.warn("[stream] failed to parse final event line", error);
          }
        }
      }

      return;
    } catch (error) {
      if (options?.signal?.aborted) {
        return;
      }
      if (attempt >= retryAttempts) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs * attempt));
    }
  }
}

export async function processAudio(audioBlob: Blob, language: string, transcriptText?: string): Promise<BackendResponse> {
  const sessionId = getOrCreateSessionId();
  const lang = normalizeApiLanguage(localStorage.getItem("language") || language || "en");
  const formData = new FormData();
  formData.append("audio", audioBlob, "recording.webm");
  if (transcriptText && transcriptText.trim()) {
    formData.append("text", transcriptText.trim());
  }
  formData.append("session_id", sessionId);
  formData.append("language", lang);
  return postForm<BackendResponse>("/api/process-audio", formData, lang);
}

export async function processOcr(file: File, language: string): Promise<OcrResponse> {
  const sessionId = getOrCreateSessionId();
  const lang = normalizeApiLanguage(language);
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);
  formData.append("language", lang);
  return postForm<OcrResponse>("/api/ocr", formData, lang);
}

export async function triggerAutofill(): Promise<{ status: string; session_id: string }> {
  const sessionId = getOrCreateSessionId();
  const response = await fetch(`${API_BASE_URL}/api/autofill`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId }),
  });

  if (!response.ok) {
    const fallback = "autofill_failed";
    try {
      const data = (await response.json()) as { detail?: string };
      throw new Error(data.detail || fallback);
    } catch {
      throw new Error(fallback);
    }
  }

  return (await response.json()) as { status: string; session_id: string };
}

export async function resetSession(sessionId: string): Promise<{ status: string; session_id: string }> {
  const response = await fetch(`${API_BASE_URL}/api/reset-session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error(`Reset session failed: ${response.status}`);
  }

  return (await response.json()) as { status: string; session_id: string };
}

export async function synthesizeTts(text: string, language: string): Promise<TtsResponse> {
  const sessionId = getOrCreateSessionId();
  const lang = normalizeApiLanguage(localStorage.getItem("language") || language || "en");
  const response = await fetch(`${API_BASE_URL}/api/tts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-language": lang,
    },
    body: JSON.stringify({ text, language: lang, session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error(`TTS request failed: ${response.status}`);
  }

  return (await response.json()) as TtsResponse;
}

export async function interruptTts(): Promise<{ session_id: string; interrupted: boolean; state: string }> {
  const sessionId = getOrCreateSessionId();
  const formData = new FormData();
  formData.append("session_id", sessionId);
  return postForm<{ session_id: string; interrupted: boolean; state: string }>("/api/tts-interrupt", formData);
}

export async function getVoiceState(): Promise<VoiceStateResponse> {
  const sessionId = getOrCreateSessionId();
  const response = await fetch(`${API_BASE_URL}/api/voice-state?session_id=${encodeURIComponent(sessionId)}`);
  if (!response.ok) {
    throw new Error(`Voice state request failed: ${response.status}`);
  }
  return (await response.json()) as VoiceStateResponse;
}
