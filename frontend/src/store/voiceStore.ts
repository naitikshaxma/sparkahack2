import { create } from "zustand";
import type { BackendResponse } from "@/services/api";

export type VoiceState = "idle" | "listening" | "processing" | "speaking" | "interrupted";

export interface LatencyIndicators {
  requestStartedAt: number | null;
  firstResponseAt: number | null;
  firstAudioChunkAt: number | null;
  lastRoundTripMs: number | null;
}

export interface ConversationTurn {
  id: string;
  userText: string;
  assistantText: string;
  mode?: "info" | "action" | "clarify";
  language: "hi" | "en";
  requestId?: string;
  createdAt: number;
}

interface VoiceStoreState {
  voiceState: VoiceState;
  transcriptLive: string;
  transcriptFinal: string;
  responseText: string;
  responseStream: string;
  streamDone: boolean;
  backendResponse: BackendResponse | null;
  errorState: string | null;
  language: "hi" | "en";
  detectedLanguage: "hi" | "en";
  latency: LatencyIndicators;
  requestId: string | null;
  demoMode: boolean;
  conversationHistory: ConversationTurn[];
}

interface VoiceStoreActions {
  setVoiceState: (voiceState: VoiceState) => void;
  setLanguage: (language: "hi" | "en") => void;
  setDetectedLanguage: (language: "hi" | "en") => void;
  setLiveTranscript: (text: string) => void;
  setFinalTranscript: (text: string) => void;
  setResponseText: (text: string) => void;
  appendResponseStream: (text: string) => void;
  clearResponseStream: () => void;
  setStreamDone: (done: boolean) => void;
  setBackendResponse: (response: BackendResponse | null) => void;
  setErrorState: (error: string | null) => void;
  beginLatencyTracking: () => void;
  markFirstResponse: () => void;
  markFirstAudioChunk: () => void;
  endLatencyTracking: () => void;
  setRequestId: (requestId: string | null) => void;
  setDemoMode: (enabled: boolean) => void;
  addConversationTurn: (turn: ConversationTurn) => void;
  updateConversationAssistantText: (turnId: string, assistantText: string) => void;
  replaceConversationHistory: (history: ConversationTurn[]) => void;
  clearConversationHistory: () => void;
  resetConversationState: () => void;
}

const initialState: VoiceStoreState = {
  voiceState: "idle",
  transcriptLive: "",
  transcriptFinal: "",
  responseText: "",
  responseStream: "",
  streamDone: false,
  backendResponse: null,
  errorState: null,
  language: "en",
  detectedLanguage: "en",
  latency: {
    requestStartedAt: null,
    firstResponseAt: null,
    firstAudioChunkAt: null,
    lastRoundTripMs: null,
  },
  requestId: null,
  demoMode: false,
  conversationHistory: [],
};

export const useVoiceStore = create<VoiceStoreState & VoiceStoreActions>((set, get) => ({
  ...initialState,

  setVoiceState: (voiceState) => set({ voiceState }),
  setLanguage: (language) => set({ language }),
  setDetectedLanguage: (detectedLanguage) => set({ detectedLanguage }),
  setLiveTranscript: (text) => set({ transcriptLive: text }),
  setFinalTranscript: (text) => set({ transcriptFinal: text }),
  setResponseText: (text) => set({ responseText: text }),
  appendResponseStream: (text) => {
    if (!text) {
      return;
    }
    set((state) => ({
      responseStream: `${state.responseStream}${state.responseStream ? " " : ""}${text.trim()}`.trim(),
    }));
  },
  clearResponseStream: () => set({ responseStream: "" }),
  setStreamDone: (streamDone) => set({ streamDone }),
  setBackendResponse: (backendResponse) => set({ backendResponse }),
  setErrorState: (errorState) => set({ errorState }),

  beginLatencyTracking: () =>
    set({
      latency: {
        requestStartedAt: performance.now(),
        firstResponseAt: null,
        firstAudioChunkAt: null,
        lastRoundTripMs: null,
      },
    }),

  markFirstResponse: () =>
    set((state) => {
      if (state.latency.firstResponseAt) {
        return state;
      }
      return {
        latency: {
          ...state.latency,
          firstResponseAt: performance.now(),
        },
      };
    }),

  markFirstAudioChunk: () =>
    set((state) => {
      if (state.latency.firstAudioChunkAt) {
        return state;
      }
      return {
        latency: {
          ...state.latency,
          firstAudioChunkAt: performance.now(),
        },
      };
    }),

  endLatencyTracking: () =>
    set((state) => {
      const started = state.latency.requestStartedAt;
      const now = performance.now();
      return {
        latency: {
          ...state.latency,
          lastRoundTripMs: started ? Math.max(0, now - started) : state.latency.lastRoundTripMs,
        },
      };
    }),

  setRequestId: (requestId) => set({ requestId }),
  setDemoMode: (demoMode) => set({ demoMode }),
  addConversationTurn: (turn) =>
    set((state) => ({
      conversationHistory: [...state.conversationHistory, turn].slice(-30),
    })),
  updateConversationAssistantText: (turnId, assistantText) =>
    set((state) => ({
      conversationHistory: state.conversationHistory.map((turn) =>
        turn.id === turnId ? { ...turn, assistantText } : turn,
      ),
    })),
  replaceConversationHistory: (conversationHistory) => set({ conversationHistory }),
  clearConversationHistory: () => set({ conversationHistory: [] }),

  resetConversationState: () => {
    const language = get().language;
    const demoMode = get().demoMode;
    set({
      ...initialState,
      language,
      detectedLanguage: language,
      demoMode,
    });
  },
}));
