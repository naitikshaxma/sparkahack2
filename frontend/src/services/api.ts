type MetaEnv = {
  DEV?: boolean;
  VITE_API_BASE_URL?: string;
  VITE_BACKEND_URL?: string;
};

import { API_BASE } from "../api";

const meta = import.meta as ImportMeta & { env?: MetaEnv };
const fallbackEnv = (globalThis as { __APP_ENV__?: MetaEnv }).__APP_ENV__ ?? {};
const env = meta.env ?? fallbackEnv;

const ENV_BACKEND_URL = env.VITE_API_BASE_URL || env.VITE_BACKEND_URL || "";
const API_BASE_URL = env.DEV ? API_BASE : ENV_BACKEND_URL;
const SESSION_KEY = "voice_os_session_id";
const DEMO_MODE = false;

export function resolveApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!API_BASE_URL) {
    return normalizedPath;
  }
  return `${API_BASE_URL}${normalizedPath}`;
}

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
  status?: "ok" | "error";
  error?: string;
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
  confidence?: number;
}

interface IntentApiResponse {
  success?: boolean;
  type?: string;
  message?: string;
  data?: {
    scheme?: string;
    summary?: string;
    reason?: string;
    next_step?: string;
    mode?: string;
  };
  confidence?: number;
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
  status?: "error" | "success";
  error?: string;
}

export type ProcessTextStreamEvent =
  | { type: "meta"; payload: BackendResponse }
  | { type: "audio_chunk"; seq: number; text_segment: string; audio_base64: string }
  | { type: "done"; session_id: string }
  | { type: "interrupted"; session_id: string }
  | { type: "error"; error: string };

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

export function setSessionId(sessionId: string): void {
  if (!sessionId) {
    return;
  }
  localStorage.setItem(SESSION_KEY, sessionId);
}

function getDemoResponseText(query: string, language: "hi" | "en"): string {
  const normalized = (query || "").toLowerCase();
  const scheme = normalized.includes("pm kisan") ? "PM Kisan" : "yeh yojana";

  if (normalized.includes("apply")) {
    return language === "hi"
      ? `Aap ${scheme} ke liye online apply kar sakte hain. Official portal par form bhariye aur documents upload kijiye.`
      : `You can apply for ${scheme} online. Fill the form on the official portal and upload the required documents.`;
  }

  if (normalized.includes("document") || normalized.includes("documents")) {
    return language === "hi"
      ? `Aapko Aadhaar card, bank details aur basic KYC documents ki zarurat hogi.`
      : `You will need Aadhaar, bank details, and basic KYC documents.`;
  }

  if (normalized.includes("kitna") || normalized.includes("paisa") || normalized.includes("amount")) {
    return language === "hi"
      ? `${scheme} me aam taur par ₹6000 saalana milte hain, jo kishton me aate hain.`
      : `${scheme} typically provides ₹6000 per year, paid in installments.`;
  }

  return language === "hi"
    ? `${scheme} ek sarkari yojana hai jisme madad di jati hai. Aap aur details pooch sakte hain.`
    : `${scheme} is a government scheme that provides assistance. Ask for more details anytime.`;
}

function buildDemoResponse(text: string, language: "hi" | "en"): BackendResponse {
  const responseText = getDemoResponseText(text, language);
  const sessionId = getOrCreateSessionId();
  return {
    session_id: sessionId,
    response_text: responseText,
    voice_text: responseText,
    field_name: null,
    validation_passed: true,
    validation_error: null,
    session_complete: false,
    mode: "info",
    action: null,
    steps_done: 0,
    steps_total: 0,
    completed_fields: [],
    quick_actions: [],
    transcript: text || undefined,
    audio_base64: null,
  };
}

function buildDemoOcrResponse(language: "hi" | "en"): OcrResponse {
  const responseText = getDemoResponseText("", language);
  return {
    session_id: getOrCreateSessionId(),
    response_text: responseText,
    field_name: null,
    validation_passed: true,
    validation_error: null,
    session_complete: false,
    ocr_data: {
      full_name: null,
      aadhaar_number: null,
      date_of_birth: null,
      address: null,
      confidence: 0,
    },
  };
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

function mapIntentToBackendResponse(payload: IntentApiResponse, transcriptText: string, sessionId: string): BackendResponse {
  const rawMessage = String(payload?.message || "").trim();
  const summary = String(payload?.data?.summary || "").trim();
  const nextStep = String(payload?.data?.next_step || "").trim();
  const textBlocks = [rawMessage, summary, nextStep].filter((item) => item.length > 0);
  const responseText = textBlocks.join("\n\n") || "Only 15 hardcoded schemes are supported.";
  const detectedScheme = String(payload?.data?.scheme || "").trim();

  return {
    session_id: sessionId,
    status: payload?.success === false ? "error" : "ok",
    response_text: responseText,
    voice_text: responseText,
    field_name: null,
    validation_passed: payload?.success !== false,
    validation_error: payload?.success === false ? (rawMessage || "Request failed") : null,
    session_complete: false,
    mode: payload?.data?.mode === "clarification" ? "clarify" : "info",
    action: payload?.type || null,
    steps_done: 0,
    steps_total: 0,
    completed_fields: [],
    scheme_details: detectedScheme
      ? {
          title: detectedScheme,
          description: summary || rawMessage,
          next_step: nextStep || undefined,
        }
      : null,
    recommended_schemes: detectedScheme ? [detectedScheme] : [],
    quick_actions: [],
    transcript: transcriptText || undefined,
    audio_base64: null,
    confidence: Number(payload?.confidence || 0),
  };
}

export async function processText(text: string, language: string): Promise<BackendResponse> {
  const sessionId = getOrCreateSessionId();
  const lang = normalizeApiLanguage(localStorage.getItem("voice_os_language") || localStorage.getItem("language") || language || "en");
  if (DEMO_MODE) {
    return buildDemoResponse(text, lang);
  }
  try {
    const response = await fetch(`${API_BASE_URL}/intent`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-language": lang,
      },
      body: JSON.stringify({
        text,
        session_id: sessionId,
        language: lang,
      }),
    });
    if (!response.ok) {
      throw new Error(`Intent request failed: ${response.status}`);
    }
    const payload = (await response.json()) as IntentApiResponse;
    return mapIntentToBackendResponse(payload, text, sessionId);
  } catch {
    return buildDemoResponse(text, lang);
  }
}

export function getWebSocketUrl(sessionId: string): string {
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsBaseUrl = ENV_BACKEND_URL ? ENV_BACKEND_URL.replace(/^http/, "ws") : `${wsProtocol}//${window.location.host}`;
  return `${wsBaseUrl}/api/v1/ws/voice/${sessionId}`;
}

export class VoiceWebSocket {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private onMessage: ((event: ProcessTextStreamEvent) => void) | null = null;
  private onRequestId: ((jobId: string) => void) | null = null;
  private shouldReconnect = false;
  private reconnectTimeout: number | null = null;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  public setCallbacks(
    onMessage: (event: ProcessTextStreamEvent) => void,
    onRequestId?: (jobId: string) => void
  ) {
    this.onMessage = onMessage;
    if (onRequestId) {
      this.onRequestId = onRequestId;
    }
  }

  public connect() {
    this.shouldReconnect = true;
    if (DEMO_MODE) {
      this.shouldReconnect = false;
      return;
    }
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
      return;
    }
    this.ws = new WebSocket(getWebSocketUrl(this.sessionId));
    
    this.ws.onopen = () => {
      if (import.meta.env.DEV) {
        console.log("[WebSocket] Connected");
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "ack" && this.onRequestId && data.job_id) {
          this.onRequestId(data.job_id);
        } else if (data.type === "result") {
          const payload = data.payload as BackendResponse;
          if (this.onMessage) {
            if (payload.status === "error") {
              this.onMessage({ type: "error", error: payload.error || "Unknown error from worker" });
            } else {
              this.onMessage({ type: "meta", payload });
              if (payload.audio_base64) {
                this.onMessage({ 
                  type: "audio_chunk", 
                  seq: 0, 
                  text_segment: payload.response_text || "", 
                  audio_base64: payload.audio_base64 
                });
              }
            }
          }
        } else if (data.type === "error") {
          if (import.meta.env.DEV) {
            console.error("[WebSocket] Backend error:", data.error);
          }
          if (this.onMessage) {
            this.onMessage({ type: "error", error: data.error || "WebSocket generic error" });
          }
        } else if (data.type === "done") {
          if (this.onMessage) {
            this.onMessage({ type: "done", session_id: this.sessionId });
          }
        } else if (data.type === "cancelled") {
          if (this.onMessage) {
            this.onMessage({ type: "interrupted", session_id: this.sessionId });
          }
        }
      } catch (e) {
        if (import.meta.env.DEV) {
          console.warn("[WebSocket] Error parsing message", e);
        }
      }
    };

    this.ws.onerror = () => {
      if (import.meta.env.DEV) {
        console.warn("WebSocket error");
      }
      if (this.onMessage) {
        this.onMessage({ type: "error", error: "websocket_transport_error" });
      }
    };

    this.ws.onclose = () => {
      if (this.shouldReconnect) {
        this.reconnectTimeout = window.setTimeout(() => this.connect(), 2000);
      }
    };
  }

  private emitDemoResponse(text: string, language: string) {
    const lang = normalizeApiLanguage(language || localStorage.getItem("voice_os_language") || localStorage.getItem("language") || "en");
    const payload = buildDemoResponse(text, lang);
    if (this.onRequestId) {
      this.onRequestId(`demo-${Date.now()}`);
    }
    if (this.onMessage) {
      this.onMessage({ type: "meta", payload });
      this.onMessage({ type: "done", session_id: this.sessionId });
    }
  }

  public sendText(text: string, language: string) {
    if (DEMO_MODE) {
      this.emitDemoResponse(text, language);
      return;
    }
    const lang = normalizeApiLanguage(language);
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.connect();
      const checkInterval = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          clearInterval(checkInterval);
          this.ws.send(JSON.stringify({ text, language: lang }));
        }
      }, 100);
      setTimeout(() => clearInterval(checkInterval), 5000); // timeout after 5s
      return;
    }
    this.ws.send(JSON.stringify({ text, language: lang }));
  }

  public sendAudio(audioBase64: string, language: string, audioFormat: string = "audio/webm") {
    if (DEMO_MODE) {
      const fallback = language === "hi" ? "Aapki awaaz transcribe ho gayi." : "Your voice was transcribed.";
      this.emitDemoResponse(fallback, language);
      return;
    }
    const lang = normalizeApiLanguage(language);
    const payload = JSON.stringify({ audio_base64: audioBase64, language: lang, audio_format: audioFormat });
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.connect();
      const checkInterval = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          clearInterval(checkInterval);
          this.ws.send(payload);
        }
      }, 100);
      setTimeout(() => clearInterval(checkInterval), 5000); // timeout after 5s
      return;
    }
    this.ws.send(payload);
  }

  public interrupt() {
    if (DEMO_MODE) {
      if (this.onMessage) {
        this.onMessage({ type: "interrupted", session_id: this.sessionId });
      }
      return;
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ cancel: true }));
    }
  }

  public disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimeout !== null) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

export async function processAudio(audioBlob: Blob, language: string, transcriptText?: string): Promise<BackendResponse> {
  const lang = normalizeApiLanguage(localStorage.getItem("voice_os_language") || localStorage.getItem("language") || language || "en");
  if (DEMO_MODE) {
    return buildDemoResponse(transcriptText || "", lang);
  }
  try {
    const transcribeData = new FormData();
    transcribeData.append("audio", audioBlob, "recording.webm");
    transcribeData.append("language", lang);
    const transcribe = await postForm<{ transcript?: string }>("/transcribe", transcribeData, lang);
    const transcribedText = String(transcribe?.transcript || transcriptText || "").trim();
    const intentResult = await processText(transcribedText, lang);
    const tts = await synthesizeTts(intentResult.response_text || transcribedText, lang);
    return {
      ...intentResult,
      transcript: transcribedText,
      audio_base64: tts.audio_base64 || null,
    };
  } catch {
    return buildDemoResponse(transcriptText || "", lang);
  }
}

export async function processOcr(file: File, language: string): Promise<OcrResponse> {
  const sessionId = getOrCreateSessionId();
  const lang = normalizeApiLanguage(language);
  if (DEMO_MODE) {
    return buildDemoOcrResponse(lang);
  }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);
  formData.append("language", lang);
  try {
    return await postForm<OcrResponse>("/ocr", formData, lang);
  } catch {
    return buildDemoOcrResponse(lang);
  }
}

export async function triggerAutofill(): Promise<{ status: string; session_id: string }> {
  const sessionId = getOrCreateSessionId();
  if (DEMO_MODE) {
    return { status: "autofill_completed", session_id: sessionId };
  }
  const response = await fetch(`${API_BASE_URL}/autofill`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId }),
  });

  try {
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
  } catch {
    return { status: "autofill_failed", session_id: sessionId };
  }
}

export async function resetSession(sessionId: string): Promise<{ status: string; session_id: string }> {
  if (DEMO_MODE) {
    return { status: "reset", session_id: sessionId };
  }
  const response = await fetch(`${API_BASE_URL}/reset-session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId }),
  });

  try {
    if (!response.ok) {
      throw new Error(`Reset session failed: ${response.status}`);
    }

    return (await response.json()) as { status: string; session_id: string };
  } catch {
    return { status: "reset", session_id: sessionId };
  }
}

export async function synthesizeTts(text: string, language: string): Promise<TtsResponse> {
  const sessionId = getOrCreateSessionId();
  const lang = normalizeApiLanguage(localStorage.getItem("voice_os_language") || localStorage.getItem("language") || language || "en");
  if (DEMO_MODE) {
    return { response_text: text, audio_base64: "" };
  }
  const response = await fetch(`${API_BASE_URL}/tts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-language": lang,
    },
    body: JSON.stringify({ text, language: lang, session_id: sessionId }),
  });

  try {
    if (!response.ok) {
      throw new Error(`TTS request failed: ${response.status}`);
    }

    return (await response.json()) as TtsResponse;
  } catch {
    return { response_text: text, audio_base64: "" };
  }
}

export async function interruptTts(): Promise<{ session_id: string; interrupted: boolean; state: string }> {
  const sessionId = getOrCreateSessionId();
  const formData = new FormData();
  formData.append("session_id", sessionId);
  if (DEMO_MODE) {
    return { session_id: sessionId, interrupted: true, state: "interrupted" };
  }
  try {
    return await postForm<{ session_id: string; interrupted: boolean; state: string }>("/tts-interrupt", formData);
  } catch {
    return { session_id: sessionId, interrupted: true, state: "interrupted" };
  }
}

export async function getVoiceState(): Promise<VoiceStateResponse> {
  const sessionId = getOrCreateSessionId();
  if (DEMO_MODE) {
    return { session_id: sessionId, status: "success" };
  }
  const response = await fetch(`${API_BASE_URL}/voice-state?session_id=${encodeURIComponent(sessionId)}`);
  try {
    if (!response.ok) {
      throw new Error(`Voice state request failed: ${response.status}`);
    }
    return (await response.json()) as VoiceStateResponse;
  } catch {
    return { session_id: sessionId, status: "success" };
  }
}
