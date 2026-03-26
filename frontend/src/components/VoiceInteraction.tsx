import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Mic, RotateCcw, Sparkles } from "lucide-react";
import BackButton from "./BackButton";
import ActionCard from "./ActionCard";
import KnowledgeCard from "./KnowledgeCard";
import ModeIndicator from "./ModeIndicator";
import QuickActions from "./QuickActions";
import ConversationHistory from "./ConversationHistory";
import OnboardingPanel from "./OnboardingPanel";
import DebugPanel from "./DebugPanel";
import {
  clearSessionId,
  getOrCreateSessionId,
  interruptTts,
  ProcessTextStreamEvent,
  processText,
  processTextStream,
  resetSession,
  synthesizeTts,
} from "@/services/api";
import { useVoiceStore } from "@/store/voiceStore";
import { detectTextLanguage, getFriendlyError, getGreeting } from "@/lib/languageUtils";
import { logFrontendEvent } from "@/services/frontendTelemetry";
import type { ConversationTurn } from "@/store/voiceStore";

const SparkleBackground = import.meta.env.MODE === "test"
  ? (() => null)
  : lazy(() => import("./result/SparkleBackground"));

interface Language {
  code: string;
  name: string;
  nativeName: string;
  greeting: string;
}

interface VoiceInteractionProps {
  language: Language;
  onBack: () => void;
}

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionEventLike = {
  resultIndex?: number;
  results: ArrayLike<{
    isFinal?: boolean;
    0: { transcript: string };
  }>;
};

const MAX_AUDIO_QUEUE = 24;

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const win = window as Window & {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return win.SpeechRecognition || win.webkitSpeechRecognition || null;
}

const VoiceInteraction = ({ language, onBack }: VoiceInteractionProps) => {
  const selectedLanguage = localStorage.getItem("language") || language.code || "en";
  const uiLanguage = selectedLanguage === "hi" ? "hi" : "en";

  const state = useVoiceStore((s) => s.voiceState);
  const transcriptLive = useVoiceStore((s) => s.transcriptLive);
  const transcriptFinal = useVoiceStore((s) => s.transcriptFinal);
  const assistantText = useVoiceStore((s) => s.responseText);
  const responseStream = useVoiceStore((s) => s.responseStream);
  const response = useVoiceStore((s) => s.backendResponse);
  const errorState = useVoiceStore((s) => s.errorState);
  const detectedLanguage = useVoiceStore((s) => s.detectedLanguage);
  const latency = useVoiceStore((s) => s.latency);
  const demoMode = useVoiceStore((s) => s.demoMode);
  const conversationHistory = useVoiceStore((s) => s.conversationHistory);

  const setVoiceState = useVoiceStore((s) => s.setVoiceState);
  const setLanguage = useVoiceStore((s) => s.setLanguage);
  const setDetectedLanguage = useVoiceStore((s) => s.setDetectedLanguage);
  const setLiveTranscript = useVoiceStore((s) => s.setLiveTranscript);
  const setFinalTranscript = useVoiceStore((s) => s.setFinalTranscript);
  const setResponseText = useVoiceStore((s) => s.setResponseText);
  const appendResponseStream = useVoiceStore((s) => s.appendResponseStream);
  const clearResponseStream = useVoiceStore((s) => s.clearResponseStream);
  const setStreamDone = useVoiceStore((s) => s.setStreamDone);
  const setBackendResponse = useVoiceStore((s) => s.setBackendResponse);
  const setErrorState = useVoiceStore((s) => s.setErrorState);
  const beginLatencyTracking = useVoiceStore((s) => s.beginLatencyTracking);
  const markFirstResponse = useVoiceStore((s) => s.markFirstResponse);
  const markFirstAudioChunk = useVoiceStore((s) => s.markFirstAudioChunk);
  const endLatencyTracking = useVoiceStore((s) => s.endLatencyTracking);
  const setRequestId = useVoiceStore((s) => s.setRequestId);
  const setDemoMode = useVoiceStore((s) => s.setDemoMode);
  const addConversationTurn = useVoiceStore((s) => s.addConversationTurn);
  const updateConversationAssistantText = useVoiceStore((s) => s.updateConversationAssistantText);
  const replaceConversationHistory = useVoiceStore((s) => s.replaceConversationHistory);
  const clearConversationHistory = useVoiceStore((s) => s.clearConversationHistory);
  const resetConversationState = useVoiceStore((s) => s.resetConversationState);

  const [micPulseKey, setMicPulseKey] = useState(0);
  const [textFallback, setTextFallback] = useState("");

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioQueueRef = useRef<Array<{ audio: string; text: string }>>([]);
  const drainingQueueRef = useRef(false);
  const hasPlayedGreetingRef = useRef(false);
  const requestCounterRef = useRef(0);
  const playbackCounterRef = useRef(0);
  const processingRef = useRef(false);
  const lastTranscriptRef = useRef<{ text: string; ts: number }>({ text: "", ts: 0 });
  const typingQueueRef = useRef<string[]>([]);
  const typingTimerRef = useRef<number | null>(null);
  const activeTurnIdRef = useRef<string | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

  const quickPrompts = useMemo(() => {
    if (demoMode) {
      return uiLanguage === "hi"
        ? [
          "मुझे PM Kisan की जानकारी चाहिए",
          "आवेदन शुरू करें",
          "मेरी एप्लिकेशन स्टेटस बताइए",
        ]
        : [
          "I need PM Kisan information",
          "Start application",
          "Check my application status",
        ];
    }

    return uiLanguage === "hi"
      ? ["Loan apply karna hai", "PM Kisan kya hai", "Pension scheme"]
      : ["I want to apply for a loan", "What is PM Kisan?", "Tell me pension scheme"];
  }, [demoMode, uiLanguage]);

  useEffect(() => {
    const sessionId = getOrCreateSessionId();
    const key = `voice_history_${sessionId}`;
    const raw = localStorage.getItem(key);
    if (!raw) {
      replaceConversationHistory([]);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as ConversationTurn[];
      if (Array.isArray(parsed)) {
        replaceConversationHistory(parsed.slice(-30));
      }
    } catch {
      replaceConversationHistory([]);
    }
  }, [replaceConversationHistory]);

  useEffect(() => {
    const sessionId = getOrCreateSessionId();
    const key = `voice_history_${sessionId}`;
    localStorage.setItem(key, JSON.stringify(conversationHistory.slice(-30)));
  }, [conversationHistory]);

  const stopTyping = useCallback(() => {
    typingQueueRef.current = [];
    if (typingTimerRef.current !== null) {
      window.clearInterval(typingTimerRef.current);
      typingTimerRef.current = null;
    }
  }, []);

  const enqueueTyping = useCallback(
    (segment: string) => {
      const words = (segment || "").trim().split(/\s+/).filter(Boolean);
      if (words.length === 0) {
        return;
      }

      typingQueueRef.current.push(...words);
      if (typingTimerRef.current !== null) {
        return;
      }

      typingTimerRef.current = window.setInterval(() => {
        const nextWord = typingQueueRef.current.shift();
        if (!nextWord) {
          if (typingTimerRef.current !== null) {
            window.clearInterval(typingTimerRef.current);
            typingTimerRef.current = null;
          }
          return;
        }
        appendResponseStream(nextWord);
      }, 70);
    },
    [appendResponseStream],
  );

  const stopListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return;
    }

    recognition.onresult = null;
    recognition.onerror = null;
    recognition.onend = null;
    try {
      recognition.stop();
    } catch {
      // no-op
    }
    recognitionRef.current = null;
  }, []);

  const stopAudio = useCallback(() => {
    playbackCounterRef.current += 1;
    audioQueueRef.current = [];
    drainingQueueRef.current = false;
    stopTyping();
    if (!audioRef.current) return;
    try {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    } catch {
      // no-op
    }
    audioRef.current = null;
  }, [stopTyping]);

  const abortActiveStream = useCallback(() => {
    if (streamAbortRef.current) {
      streamAbortRef.current.abort();
      streamAbortRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      abortActiveStream();
    };
  }, [abortActiveStream]);

  const playQueue = useCallback(async () => {
    if (drainingQueueRef.current) {
      return;
    }
    drainingQueueRef.current = true;
    const playbackId = playbackCounterRef.current;

    try {
      while (audioQueueRef.current.length > 0 && playbackId === playbackCounterRef.current) {
        const chunk = audioQueueRef.current.shift();
        if (!chunk) {
          continue;
        }

        const src = chunk.audio.startsWith("data:audio") ? chunk.audio : `data:audio/mp3;base64,${chunk.audio}`;
        enqueueTyping(chunk.text);
        await new Promise<void>((resolve) => {
          const audio = new Audio(src);
          audioRef.current = audio;
          audio.onended = () => resolve();
          audio.onerror = () => resolve();
          void audio.play().catch(() => resolve());
        });
      }
    } finally {
      drainingQueueRef.current = false;
      if (playbackId === playbackCounterRef.current) {
        setVoiceState("idle");
      }
    }
  }, [enqueueTyping, setVoiceState]);

  const enqueueAudioChunk = useCallback((audioBase64?: string | null, textSegment = "") => {
    if (!audioBase64) {
      return;
    }

    stopListening();
    if (audioQueueRef.current.length >= MAX_AUDIO_QUEUE) {
      audioQueueRef.current = audioQueueRef.current.slice(-Math.floor(MAX_AUDIO_QUEUE / 2));
      logFrontendEvent("audio_queue_trimmed", { size: audioQueueRef.current.length }, getOrCreateSessionId());
    }
    audioQueueRef.current.push({ audio: audioBase64, text: textSegment });
    setVoiceState("speaking");
    void playQueue();
  }, [playQueue, setVoiceState, stopListening]);

  const playAudioFromBase64 = useCallback(
    async (audioBase64?: string | null) => {
      if (!audioBase64) return;

      // Always stop active recognition while assistant is speaking.
      stopListening();
      stopAudio();

      const playbackId = playbackCounterRef.current;
      setVoiceState("speaking");

      const src = audioBase64.startsWith("data:audio") ? audioBase64 : `data:audio/mp3;base64,${audioBase64}`;

      await new Promise<void>((resolve) => {
        const audio = new Audio(src);
        audioRef.current = audio;

        audio.onended = () => {
          if (playbackId === playbackCounterRef.current) {
            setVoiceState("idle");
          }
          resolve();
        };

        audio.onerror = () => {
          if (playbackId === playbackCounterRef.current) {
            setVoiceState("idle");
          }
          resolve();
        };

        void audio.play().catch(() => {
          if (playbackId === playbackCounterRef.current) {
            setVoiceState("idle");
          }
          resolve();
        });
      });
    },
    [setVoiceState, stopAudio, stopListening],
  );

  const speakText = useCallback(
    async (text: string) => {
      try {
        const tts = await synthesizeTts(text, uiLanguage);
        await playAudioFromBase64(tts.audio_base64);
      } catch {
        setVoiceState("idle");
      }
    },
    [playAudioFromBase64, setVoiceState, uiLanguage],
  );

  const handleTranscript = useCallback(
    async (text: string) => {
      const cleaned = (text || "").trim();
      if (!cleaned || processingRef.current) {
        return;
      }

      const now = Date.now();
      if (lastTranscriptRef.current.text === cleaned && now - lastTranscriptRef.current.ts < 1500) {
        return;
      }
      lastTranscriptRef.current = { text: cleaned, ts: now };

      abortActiveStream();
      setFinalTranscript(cleaned);
      setLiveTranscript("");
      const inputLanguage = detectTextLanguage(cleaned);
      setDetectedLanguage(inputLanguage);
      logFrontendEvent("language_detected", { source: "transcript", inputLanguage }, getOrCreateSessionId());

      beginLatencyTracking();
      setVoiceState("processing");
      processingRef.current = true;
      const requestId = ++requestCounterRef.current;
      const turnId = `turn-${Date.now()}-${requestId}`;
      activeTurnIdRef.current = turnId;
      addConversationTurn({
        id: turnId,
        userText: cleaned,
        assistantText: "",
        language: uiLanguage,
        createdAt: Date.now(),
      });
      clearResponseStream();
      setStreamDone(false);
      setErrorState(null);
      setResponseText("");

      let doneSeen = false;
      const controller = new AbortController();
      streamAbortRef.current = controller;
      try {
        await processTextStream(
          cleaned,
          uiLanguage,
          (event: ProcessTextStreamEvent) => {
            if (requestId !== requestCounterRef.current) {
              return;
            }

            if (event.type === "meta") {
              const payload = event.payload;
              markFirstResponse();
              setBackendResponse(payload);
              setResponseText(payload.response_text || "");
              setDetectedLanguage(detectTextLanguage(payload.response_text || ""));
              updateConversationAssistantText(turnId, payload.response_text || "");
              processingRef.current = false;
              setVoiceState("idle");
              return;
            }

            if (event.type === "audio_chunk") {
              markFirstAudioChunk();
              logFrontendEvent("stream_first_chunk", { seq: event.seq }, getOrCreateSessionId());
              enqueueAudioChunk(event.audio_base64, event.text_segment || "");
              return;
            }

            if (event.type === "interrupted") {
              abortActiveStream();
              stopAudio();
              setVoiceState("interrupted");
              return;
            }

            if (event.type === "done") {
              doneSeen = true;
              setStreamDone(true);
              logFrontendEvent("stream_done", { requestId }, getOrCreateSessionId());
              if (!drainingQueueRef.current && audioQueueRef.current.length === 0) {
                setVoiceState("idle");
              }
            }
          },
          (incomingRequestId) => {
            setRequestId(incomingRequestId);
            updateConversationAssistantText(turnId, useVoiceStore.getState().responseText || "");
          },
          {
            signal: controller.signal,
            retryAttempts: 2,
            retryDelayMs: 300,
          },
        );
        if (!doneSeen && requestId === requestCounterRef.current && !controller.signal.aborted) {
          setStreamDone(true);
          if (!drainingQueueRef.current && audioQueueRef.current.length === 0) {
            setVoiceState("idle");
          }
        }
      } catch {
        try {
          const response = await processText(cleaned, uiLanguage);
          if (requestId !== requestCounterRef.current) {
            return;
          }
          setBackendResponse(response);
          setResponseText(response.response_text || "");
          setDetectedLanguage(detectTextLanguage(response.response_text || ""));
          setRequestId(response.request_id || null);
          updateConversationAssistantText(turnId, response.response_text || "");
          processingRef.current = false;
          setVoiceState("idle");
          if (response.audio_base64) {
            enqueueTyping(response.response_text || "");
            void playAudioFromBase64(response.audio_base64);
          }
        } catch {
          if (requestId !== requestCounterRef.current) {
            return;
          }
          processingRef.current = false;
          setVoiceState("idle");
          setErrorState(getFriendlyError("network", uiLanguage));
          updateConversationAssistantText(turnId, uiLanguage === "hi" ? "नेटवर्क समस्या हुई, कृपया फिर से कोशिश करें।" : "Network issue, please retry.");
          logFrontendEvent("error", { phase: "process_text" }, getOrCreateSessionId());
        }
      } finally {
        if (streamAbortRef.current === controller) {
          streamAbortRef.current = null;
        }
        endLatencyTracking();
      }
    },
    [
      abortActiveStream,
      beginLatencyTracking,
      addConversationTurn,
      clearResponseStream,
      endLatencyTracking,
      enqueueAudioChunk,
      enqueueTyping,
      markFirstAudioChunk,
      markFirstResponse,
      playAudioFromBase64,
      stopAudio,
      setBackendResponse,
      setDetectedLanguage,
      setErrorState,
      setRequestId,
      setFinalTranscript,
      setLiveTranscript,
      setResponseText,
      setStreamDone,
      setVoiceState,
      updateConversationAssistantText,
      uiLanguage,
    ],
  );

  const startListening = useCallback(() => {
    if (processingRef.current || state === "processing" || state === "speaking" || state === "listening") {
      return;
    }

    const SpeechRecognition = getSpeechRecognitionCtor();
    if (!SpeechRecognition) {
      setErrorState(uiLanguage === "hi" ? "इस ब्राउज़र में वॉइस सपोर्ट नहीं है।" : "Voice recognition is not supported in this browser.");
      return;
    }

    stopListening();
    stopAudio();
    setErrorState(null);

    const recognition = new SpeechRecognition();
    recognition.lang = uiLanguage === "hi" ? "hi-IN" : "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onresult = (event) => {
      let text = "";
      let interim = "";
      const startIndex = event.resultIndex ?? 0;
      for (let idx = startIndex; idx < event.results.length; idx += 1) {
        const result = event.results[idx];
        if (result?.isFinal) {
          text += `${result[0]?.transcript || ""} `;
        } else {
          interim += `${result[0]?.transcript || ""} `;
        }
      }
      setLiveTranscript(interim.trim());
      text = text.trim();

      if (!text) {
        return;
      }

      if (text.length < 2) {
        setVoiceState("idle");
        setErrorState(uiLanguage === "hi" ? "आवाज़ स्पष्ट नहीं थी, फिर से बोलें।" : "Speech was unclear, please try again.");
        return;
      }

      recognitionRef.current = null;
      setVoiceState("idle");
      void handleTranscript(text);
    };

    recognition.onerror = () => {
      recognitionRef.current = null;
      setVoiceState("idle");
      setErrorState(uiLanguage === "hi" ? "वॉइस रिकग्निशन असफल रहा, फिर से कोशिश करें।" : "Speech recognition failed. Please try again.");
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      setLiveTranscript("");
      if (useVoiceStore.getState().voiceState === "listening") {
        setVoiceState("idle");
      }
    };

    recognitionRef.current = recognition;
    setVoiceState("listening");
    logFrontendEvent("voice_state", { state: "listening" }, getOrCreateSessionId());
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setVoiceState("idle");
      setErrorState(uiLanguage === "hi" ? "माइक चालू नहीं हो पाया, फिर से कोशिश करें।" : "Could not start microphone. Please try again.");
    }
  }, [handleTranscript, setErrorState, setLiveTranscript, setVoiceState, state, stopAudio, stopListening, uiLanguage]);

  const handleMicClick = useCallback(() => {
    setMicPulseKey((prev) => prev + 1);
    logFrontendEvent("mic_tap", { state }, getOrCreateSessionId());
    if (state === "speaking") {
      stopAudio();
      setVoiceState("interrupted");
      setLiveTranscript("");
      logFrontendEvent("barge_in", {}, getOrCreateSessionId());
      void interruptTts().catch(() => undefined);
      window.setTimeout(() => {
        startListening();
      }, 80);
      return;
    }
    startListening();
  }, [setLiveTranscript, setVoiceState, startListening, state, stopAudio]);

  const handleRestart = useCallback(async () => {
    stopListening();
    stopAudio();
    requestCounterRef.current += 1;
    processingRef.current = false;
    lastTranscriptRef.current = { text: "", ts: 0 };

    const previousSessionId = getOrCreateSessionId();
    try {
      await resetSession(previousSessionId);
    } catch {
      // Ignore reset errors; we still rotate client session id.
    }

    clearSessionId();
    const nextSessionId = getOrCreateSessionId();
    localStorage.removeItem(`voice_history_${previousSessionId}`);
    localStorage.removeItem(`voice_history_${nextSessionId}`);

    resetConversationState();
    clearConversationHistory();
    setVoiceState("idle");
    setRequestId(null);
    setTextFallback("");

    const greeting = getGreeting(uiLanguage);
    setResponseText(greeting);
    clearResponseStream();
    void speakText(greeting);
  }, [
    clearConversationHistory,
    clearResponseStream,
    resetConversationState,
    setRequestId,
    setResponseText,
    setVoiceState,
    speakText,
    stopAudio,
    stopListening,
    uiLanguage,
  ]);

  useEffect(() => {
    if (hasPlayedGreetingRef.current) return;
    hasPlayedGreetingRef.current = true;
    setLanguage(uiLanguage);
    setDetectedLanguage(uiLanguage);

    const greeting = getGreeting(uiLanguage);

    setResponseText(greeting);
    void speakText(greeting);
  }, [setDetectedLanguage, setLanguage, setResponseText, speakText, uiLanguage]);

  useEffect(() => {
    return () => {
      stopListening();
      stopAudio();
      stopTyping();
    };
  }, [stopAudio, stopListening, stopTyping]);

  useEffect(() => {
    if (!latency.lastRoundTripMs) {
      return;
    }
    logFrontendEvent(
      "latency",
      {
        roundTripMs: Math.round(latency.lastRoundTripMs),
        firstResponseMs: latency.requestStartedAt && latency.firstResponseAt
          ? Math.round(latency.firstResponseAt - latency.requestStartedAt)
          : null,
        firstAudioChunkMs: latency.requestStartedAt && latency.firstAudioChunkAt
          ? Math.round(latency.firstAudioChunkAt - latency.requestStartedAt)
          : null,
      },
      getOrCreateSessionId(),
    );
  }, [latency.firstAudioChunkAt, latency.firstResponseAt, latency.lastRoundTripMs, latency.requestStartedAt]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (event.code === "Space" || event.code === "Enter") {
        event.preventDefault();
        handleMicClick();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [handleMicClick]);

  const statusText =
    state === "listening"
      ? uiLanguage === "hi"
        ? "🎤 सुन रहा हूँ..."
        : "🎤 Listening..."
      : state === "processing"
        ? uiLanguage === "hi"
          ? "🤖 सोच रहा हूँ..."
          : "🤖 Thinking..."
      : state === "speaking"
        ? uiLanguage === "hi"
          ? "🔊 जवाब दे रहा हूँ..."
          : "🔊 Speaking..."
        : state === "interrupted"
          ? uiLanguage === "hi"
            ? "⏹ रोका गया, अब बोलें"
            : "⏹ Interrupted, speak now"
        : uiLanguage === "hi"
          ? "माइक दबाकर बोलें"
          : "Tap mic to speak";

  const statusSubText = useMemo(() => {
    if (state === "listening") {
      return uiLanguage === "hi" ? "हम आपकी आवाज़ कैप्चर कर रहे हैं" : "We are capturing your voice";
    }
    if (state === "processing") {
      return uiLanguage === "hi" ? "तुरंत जवाब तैयार हो रहा है" : "Preparing an instant response";
    }
    if (state === "speaking") {
      return uiLanguage === "hi" ? "जवाब बोल रहा हूँ, टैप करके रोक सकते हैं" : "Speaking now, tap mic to interrupt";
    }
    if (state === "interrupted") {
      return uiLanguage === "hi" ? "अब आप बोल सकते हैं" : "You can speak now";
    }
    return uiLanguage === "hi" ? "स्पेस या एंटर दबाकर भी शुरू कर सकते हैं" : "You can also press Space or Enter to start";
  }, [state, uiLanguage]);

  const mode = response?.mode;
  const quickActions = response?.quick_actions || [];
  const schemeDetails = response?.scheme_details;
  const stepsDone = response?.steps_done || 0;
  const stepsTotal = response?.steps_total || 0;
  const completedFields = response?.completed_fields || [];

  const handleQuickAction = useCallback((value: string) => {
    if (!value || state !== "idle") {
      return;
    }
    logFrontendEvent("quick_action", { value }, getOrCreateSessionId());
    void handleTranscript(value);
  }, [handleTranscript, state]);

  const clarifyPrimary = quickActions.find((item) => item.value === "need_information") || {
    label: uiLanguage === "hi" ? "जानकारी चाहिए" : "Get Information",
    value: "need_information",
  };
  const clarifySecondary = quickActions.find((item) => item.value === "start_application") || {
    label: uiLanguage === "hi" ? "आवेदन शुरू करें" : "Apply Now",
    value: "start_application",
  };
  const showEmptySuggestions = !response && !transcriptFinal;
  const displayedAssistantText = responseStream || assistantText;
  const effectiveErrorText = errorState || "";
  const showOnboarding = conversationHistory.length === 0 && !transcriptFinal && state === "idle";

  const submitFallbackText = useCallback(() => {
    const cleaned = textFallback.trim();
    if (!cleaned || state === "processing") {
      return;
    }
    setTextFallback("");
    void handleTranscript(cleaned);
  }, [handleTranscript, state, textFallback]);

  const retryLast = useCallback(() => {
    if (!transcriptFinal) {
      return;
    }
    void handleTranscript(transcriptFinal);
  }, [handleTranscript, transcriptFinal]);

  const firstResponseMs = latency.requestStartedAt && latency.firstResponseAt
    ? Math.max(0, Math.round(latency.firstResponseAt - latency.requestStartedAt))
    : null;
  const firstAudioMs = latency.requestStartedAt && latency.firstAudioChunkAt
    ? Math.max(0, Math.round(latency.firstAudioChunkAt - latency.requestStartedAt))
    : null;

  useEffect(() => {
    const turnId = activeTurnIdRef.current;
    if (!turnId) {
      return;
    }
    if (!displayedAssistantText) {
      return;
    }
    updateConversationAssistantText(turnId, displayedAssistantText);
  }, [displayedAssistantText, updateConversationAssistantText]);

  return (
    <div className="h-screen bg-[radial-gradient(circle_at_top,#134e4a30_0%,#0b1120_35%,#030712_100%)] flex flex-col relative text-[#e2e8f0] overflow-hidden" role="application" aria-label="Voice assistant interface">
      <Suspense fallback={null}>
        <SparkleBackground />
      </Suspense>

      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(160deg,rgba(245,158,11,0.1),transparent_35%,rgba(20,184,166,0.12)_80%)]" />
      <div className="pointer-events-none absolute -top-28 -left-20 w-72 h-72 rounded-full bg-[#f59e0b]/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-20 w-80 h-80 rounded-full bg-[#14b8a6]/10 blur-3xl" />

      <div className="relative z-10 flex items-center justify-between px-3 md:px-4 py-1.5 border-b border-white/10 bg-black/35 backdrop-blur-xl">
        <BackButton onClick={onBack} label={uiLanguage === "hi" ? "भाषा बदलें" : "Change language"} />
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2 text-white">
            <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-[#f59e0b] to-[#fb7185] grid place-items-center shadow-[0_0_16px_rgba(245,158,11,0.35)]">
              <Mic className="w-3.5 h-3.5 text-black" />
            </div>
            <span className="font-semibold tracking-wide bg-gradient-to-r from-yellow-300 to-rose-300 text-transparent bg-clip-text">Voice OS Bharat</span>
            <div className="ml-1 flex items-center gap-2 px-3 py-1 rounded-full border bg-white/5 text-xs font-medium border-[#f59e0b]/40 text-[#f59e0b]">
              <Sparkles className="w-3.5 h-3.5" />
              {language.nativeName}
            </div>
            <div className="ml-1 px-2.5 py-1 rounded-full border border-cyan-300/40 bg-cyan-500/10 text-cyan-100 text-[11px] font-semibold">
              {detectedLanguage === "hi" ? "Detected: हिन्दी" : "Detected: English"}
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              void handleRestart();
            }}
            className="ml-1 inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-white/20 bg-white/10 text-white text-xs hover:border-[#f59e0b]/60 hover:shadow-[0_0_14px_rgba(245,158,11,0.25)] transition-all"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            {uiLanguage === "hi" ? "रीस्टार्ट" : "Restart"}
          </button>
          <button
            type="button"
            onClick={() => setDemoMode(!demoMode)}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-cyan-300/35 bg-cyan-500/10 text-cyan-100 text-xs hover:bg-cyan-500/20 transition-all"
          >
            {demoMode ? (uiLanguage === "hi" ? "डेमो मोड ऑन" : "Demo Mode On") : (uiLanguage === "hi" ? "डेमो मोड" : "Demo Mode")}
          </button>
        </div>
      </div>

      <div className="relative z-10 flex-1 min-h-0 flex flex-col items-center justify-center px-4 py-4">
        <div className="w-full max-w-3xl rounded-3xl border border-white/10 bg-white/[0.06] backdrop-blur-2xl px-4 md:px-7 py-5 space-y-5 shadow-[0_24px_70px_rgba(0,0,0,0.45)]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold border border-cyan-300/40 bg-cyan-500/10 text-cyan-100">AI-powered</span>
            <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold border border-emerald-300/40 bg-emerald-500/10 text-emerald-100">Bilingual</span>
            {mode ? <ModeIndicator mode={mode} /> : null}
            <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold border border-amber-300/40 bg-amber-500/10 text-amber-100">{uiLanguage === "hi" ? "सहायक: सखी" : "Assistant: Sakhi"}</span>
          </div>

          {showOnboarding ? (
            <OnboardingPanel
              uiLanguage={uiLanguage}
              onSamplePick={(query) => {
                void handleTranscript(query);
              }}
            />
          ) : null}

          <div className="space-y-1.5">
            <h2 className="text-2xl md:text-3xl font-semibold text-white leading-tight animate-[fadeIn_360ms_ease-out]">
              {uiLanguage === "hi" ? "आइए, आपकी आवाज़ से शुरुआत करें" : "Let us start with your voice"}
            </h2>
            <p className="text-sm text-gray-300 animate-[fadeIn_420ms_ease-out]" aria-live="polite" role="status">{statusText}</p>
            <p className="text-xs text-gray-400">{statusSubText}</p>
            <div className="flex flex-wrap gap-2 text-[11px] text-cyan-100/90">
              {firstResponseMs !== null ? <span className="px-2 py-0.5 rounded-full border border-cyan-300/30 bg-cyan-500/10">First response: {firstResponseMs}ms</span> : null}
              {firstAudioMs !== null ? <span className="px-2 py-0.5 rounded-full border border-emerald-300/30 bg-emerald-500/10">First audio: {firstAudioMs}ms</span> : null}
              {latency.lastRoundTripMs ? <span className="px-2 py-0.5 rounded-full border border-amber-300/30 bg-amber-500/10">Round trip: {Math.round(latency.lastRoundTripMs)}ms</span> : null}
            </div>
          </div>

          <div className="grid place-items-center py-2">
            <div className="relative">
              {micPulseKey > 0 ? (
                <span
                  key={micPulseKey}
                  className="absolute -inset-12 rounded-full border border-[#f59e0b]/45 animate-ping"
                />
              ) : null}
              {state === "listening" && (
                <>
                  <div className="absolute -inset-8 rounded-full bg-[#f59e0b]/20 blur-xl animate-pulse" />
                  <div className="absolute -inset-12 rounded-full border border-[#f59e0b]/30 animate-ping" />
                </>
              )}
              {state === "speaking" && (
                <>
                  <div className="absolute -inset-8 rounded-full bg-[#14b8a6]/20 blur-xl animate-pulse" />
                  <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 flex items-end gap-1.5">
                    <span className="w-1.5 h-4 rounded-full bg-teal-300/80 animate-pulse" />
                    <span className="w-1.5 h-6 rounded-full bg-teal-200/90 animate-pulse [animation-delay:120ms]" />
                    <span className="w-1.5 h-3 rounded-full bg-teal-300/80 animate-pulse [animation-delay:240ms]" />
                  </div>
                </>
              )}
              <button
                type="button"
                onClick={handleMicClick}
                disabled={state === "processing"}
                aria-label={uiLanguage === "hi" ? "माइक्रोफ़ोन नियंत्रित करें" : "Control microphone"}
                aria-pressed={state === "listening"}
                className="relative z-10 w-36 h-36 md:w-40 md:h-40 rounded-full border border-white/20 bg-gradient-to-br from-[#0f172a] to-[#111827] text-white grid place-items-center shadow-[0_18px_60px_rgba(0,0,0,0.55)] disabled:opacity-55 hover:scale-105 hover:shadow-[0_0_24px_rgba(245,158,11,0.28)] active:scale-95 transition-all"
              >
                <Mic className="w-12 h-12" />
              </button>
            </div>
          </div>

          {mode === "action" && stepsTotal > 0 ? (
            <ActionCard
              stepsDone={stepsDone}
              stepsTotal={stepsTotal}
              completedFields={completedFields}
              uiLanguage={uiLanguage}
            />
          ) : null}

          {mode === "info" && schemeDetails ? (
            <KnowledgeCard
              uiLanguage={uiLanguage}
              title={schemeDetails.title}
              description={schemeDetails.description}
              eligibility={schemeDetails.next_step}
            />
          ) : null}

          {mode === "clarify" ? (
            <div className="rounded-2xl border border-amber-300/30 bg-amber-500/10 px-4 py-3 animate-[fadeIn_280ms_ease-out]">
              <p className="text-xs uppercase tracking-wide text-amber-100/85 mb-2">
                {uiLanguage === "hi" ? "कृपया विकल्प चुनें" : "Choose one option"}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={state !== "idle"}
                  onClick={() => {
                    handleQuickAction(clarifyPrimary.value);
                  }}
                  className="px-3.5 py-2 rounded-full text-xs font-semibold bg-amber-200 text-amber-900 hover:bg-amber-100 hover:shadow-[0_0_14px_rgba(251,191,36,0.45)] disabled:opacity-60 transition-all"
                >
                  {uiLanguage === "hi" ? "जानकारी चाहिए" : "Get Information"}
                </button>
                <button
                  type="button"
                  disabled={state !== "idle"}
                  onClick={() => {
                    handleQuickAction(clarifySecondary.value);
                  }}
                  className="px-3.5 py-2 rounded-full text-xs font-semibold bg-white/15 border border-white/30 text-white hover:border-amber-200/80 hover:shadow-[0_0_14px_rgba(251,191,36,0.25)] disabled:opacity-60 transition-all"
                >
                  {uiLanguage === "hi" ? "अभी आवेदन करें" : "Apply Now"}
                </button>
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2 justify-center">
            {quickActions.length > 0 && mode !== "clarify" ? (
              <QuickActions
                uiLanguage={uiLanguage}
                actions={quickActions}
                disabled={state !== "idle"}
                onSelect={handleQuickAction}
              />
            ) : showEmptySuggestions ? (
              quickPrompts.map((item) => (
                <button
                  key={item}
                  type="button"
                  disabled={state !== "idle"}
                  onClick={() => {
                    void handleTranscript(item);
                  }}
                  className="px-3 py-1.5 rounded-full text-xs border border-white/20 bg-white/10 text-white hover:border-[#f59e0b]/70 hover:shadow-[0_0_14px_rgba(245,158,11,0.28)] disabled:opacity-50 transition-all"
                >
                  {item}
                </button>
              ))
            ) : null}
          </div>

          <div className="rounded-2xl border border-white/15 bg-white/[0.08] backdrop-blur-xl px-4 py-3 min-h-[84px] animate-[fadeIn_320ms_ease-out] shadow-[0_10px_30px_rgba(0,0,0,0.22)]">
            <p className="text-[11px] uppercase tracking-wide text-gray-300 mb-1.5 font-semibold">
              {uiLanguage === "hi" ? "Assistant Reply" : "Assistant Reply"}
            </p>
            <p className="text-cyan-50 leading-relaxed text-[15px]" aria-live="polite">
              {displayedAssistantText || (uiLanguage === "hi" ? "यहाँ आपका सहायक उत्तर दिखाई देगा।" : "Your assistant response will appear here.")}
            </p>
          </div>

          <div className="rounded-xl border border-white/10 bg-black/25 px-3 py-2.5 min-h-[56px]">
            <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-1">
              {uiLanguage === "hi" ? "आपने कहा" : "You Said"}
            </p>
            <p className="text-white text-sm">{transcriptLive || transcriptFinal || (uiLanguage === "hi" ? "आपकी आवाज़ यहाँ दिखाई देगी" : "Your speech will appear here")}</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2.5">
            <p className="text-[11px] uppercase tracking-wide text-gray-400 mb-2">
              {uiLanguage === "hi" ? "वॉइस समस्या? टेक्स्ट से लिखें" : "Voice unavailable? Type your message"}
            </p>
            <div className="flex gap-2">
              <input
                value={textFallback}
                onChange={(event) => setTextFallback(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    submitFallbackText();
                  }
                }}
                placeholder={uiLanguage === "hi" ? "यहाँ लिखें..." : "Type here..."}
                className="flex-1 rounded-xl bg-[#0f172a] border border-white/15 px-3 py-2 text-sm outline-none focus:border-cyan-300/70"
                aria-label={uiLanguage === "hi" ? "टेक्स्ट इनपुट" : "Text input"}
              />
              <button
                type="button"
                onClick={submitFallbackText}
                disabled={state === "processing" || !textFallback.trim()}
                className="px-3 py-2 rounded-xl text-xs font-semibold border border-cyan-300/40 bg-cyan-500/15 text-cyan-100 disabled:opacity-50"
              >
                {uiLanguage === "hi" ? "भेजें" : "Send"}
              </button>
            </div>
          </div>

          <ConversationHistory history={conversationHistory} uiLanguage={uiLanguage} />

          {effectiveErrorText ? (
            <div className="rounded-xl border border-red-300/30 bg-red-500/10 px-3 py-2 text-red-200 text-sm animate-[fadeIn_220ms_ease-out]">
              <p>{effectiveErrorText}</p>
              <button
                type="button"
                onClick={retryLast}
                className="mt-2 rounded-full border border-red-200/40 px-3 py-1 text-xs font-semibold hover:bg-red-400/10"
              >
                {uiLanguage === "hi" ? "फिर से कोशिश करें" : "Try again"}
              </button>
            </div>
          ) : null}

        </div>
      </div>
      <DebugPanel />
    </div>
  );
};

export default VoiceInteraction;
