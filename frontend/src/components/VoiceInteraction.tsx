import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import MicButton from './MicButton';
import BackButton from './BackButton';
import { speakText, micHints } from '@/lib/voiceUtils';

const ENV_BACKEND_URL =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_BACKEND_URL ||
  '';
// In local dev, use Vite proxy to avoid CORS/origin mismatches.
const BACKEND_URL = import.meta.env.DEV ? '' : ENV_BACKEND_URL;

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

const prompts: Record<string, { speak: string; hint: string }> = {
  hi: { speak: 'Speak now...', hint: 'Listening...' },
  en: { speak: 'Speak now...', hint: 'Listening...' },
  mr: { speak: 'Speak now...', hint: 'Listening...' },
  bn: { speak: 'Speak now...', hint: 'Listening...' },
  ta: { speak: 'Speak now...', hint: 'Listening...' },
  te: { speak: 'Speak now...', hint: 'Listening...' },
  kn: { speak: 'Speak now...', hint: 'Listening...' },
  ml: { speak: 'Speak now...', hint: 'Listening...' },
  pa: { speak: 'Speak now...', hint: 'Listening...' },
  gu: { speak: 'Speak now...', hint: 'Listening...' },
};

const backLabels: Record<string, string> = {
  hi: 'Change language',
  en: 'Change language',
  mr: 'Change language',
  bn: 'Change language',
  ta: 'Change language',
  te: 'Change language',
  kn: 'Change language',
  ml: 'Change language',
  pa: 'Change language',
  gu: 'Change language',
};

const langAccents: Record<string, string> = {
  hi: '#f59e0b',
  en: '#9ca3af',
  mr: '#ea580c',
  bn: '#dc2626',
  ta: '#14b8a6',
  te: '#b91c1c',
  kn: '#16a34a',
  ml: '#7c3aed',
  pa: '#d97706',
  gu: '#2563eb',
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: any) => void) | null;
  start: () => void;
  stop: () => void;
};

/** Get or create a stable user_id in localStorage */
function getUserId(): string {
  const key = 'voice_os_user_id';
  let id = localStorage.getItem(key);
  if (!id) {
    id = `user-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    localStorage.setItem(key, id);
  }
  return id;
}

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const w = window as Window & {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

const VoiceInteraction = ({ language, onBack }: VoiceInteractionProps) => {
  const navigate = useNavigate();
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [liveTranscript, setLiveTranscript] = useState('');

  const hasGreetedRef = useRef(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const liveTranscriptRef = useRef('');

  const prompt = prompts[language.code] ?? prompts.en;
  const backLabel = backLabels[language.code] ?? backLabels.en;
  const accent = langAccents[language.code] ?? '#f59e0b';
  const hintText = micHints[language.code] ?? micHints.en;

  const stopRecognition = useCallback(() => {
    if (!recognitionRef.current) return;
    try {
      recognitionRef.current.stop();
    } catch {
      // no-op
    }
    recognitionRef.current = null;
  }, []);

  /* Cancel everything on unmount */
  const cleanupRecording = useCallback(() => {
    stopRecognition();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
    setLiveTranscript('');
    liveTranscriptRef.current = '';
  }, [stopRecognition]);

  /* Speak greeting on mount */
  useEffect(() => {
    if (!('speechSynthesis' in window)) return;
    if (hasGreetedRef.current) return;
    let cancelled = false;

    const doSpeak = (voices: SpeechSynthesisVoice[]) => {
      if (cancelled || hasGreetedRef.current) return;
      hasGreetedRef.current = true;
      speakText(
        language.greeting,
        language.code,
        voices,
        () => {
          if (!cancelled) setIsSpeaking(true);
        },
        () => {
          if (!cancelled) setIsSpeaking(false);
        },
        () => {
          if (!cancelled) setIsSpeaking(false);
        },
      );
    };

    const voices = speechSynthesis.getVoices();
    if (voices.length > 0) {
      setTimeout(() => doSpeak(voices), 200);
    } else {
      const handler = () => {
        const updatedVoices = speechSynthesis.getVoices();
        if (updatedVoices.length > 0) {
          doSpeak(updatedVoices);
          speechSynthesis.removeEventListener('voiceschanged', handler);
        }
      };
      speechSynthesis.addEventListener('voiceschanged', handler);
      setTimeout(() => {
        if (!hasGreetedRef.current) doSpeak(speechSynthesis.getVoices());
      }, 1000);
    }

    return () => {
      cancelled = true;
      speechSynthesis.cancel();
      cleanupRecording();
    };
  }, [language, cleanupRecording]);

  const navigateToResult = useCallback(
    (data: any) => {
      navigate('/result', {
        state: {
          language: language.name,
          languageCode: language.code,
          transcript: data.transcript,
          intent: data.intent,
          confidence: data.confidence,
          response_text: data.response_text,
          audio_base64: data.audio_base64,
        },
      });
    },
    [language, navigate],
  );

  /** Send recorded audio and optionally live transcript (if available). */
  const sendAudioToBackend = useCallback(
    async (audioBlob: Blob, transcriptText?: string) => {
      setIsProcessing(true);
      setErrorMsg('');

      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');
      if (transcriptText?.trim()) {
        formData.append('text', transcriptText.trim());
      }
      formData.append('user_id', getUserId());
      formData.append('language', language.code);

      try {
        const response = await fetch(`${BACKEND_URL}/api/process-audio`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`Backend error: ${response.status}`);
        }

        const data = await response.json();
        navigateToResult(data);
      } catch (err) {
        console.error('Audio processing failed:', err);
        setErrorMsg('Could not reach the voice assistant. Please check the backend is running.');
        setIsProcessing(false);
      }
    },
    [language, navigateToResult],
  );

  /** Start or stop recording */
  const handleMicClick = useCallback(async () => {
    if (isProcessing) return;

    // STOP recording
    if (isListening) {
      stopRecognition();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    // Cancel any ongoing speech synthesis
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    setIsSpeaking(false);
    setErrorMsg('');
    setLiveTranscript('');
    liveTranscriptRef.current = '';

    // REQUEST microphone
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch {
      setErrorMsg('Microphone access denied. Please allow microphone access and try again.');
      return;
    }

    streamRef.current = stream;
    audioChunksRef.current = [];

    // Pick best supported MIME type
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : '';

    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    mediaRecorderRef.current = recorder;

    const SpeechRecognitionCtor = getSpeechRecognitionCtor();
    if (SpeechRecognitionCtor) {
      const recognition = new SpeechRecognitionCtor();
      recognition.lang = language.code === 'en' ? 'en-IN' : `${language.code}-IN`;
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.onresult = (event: any) => {
        const text = Array.from(event.results || [])
          .map((result: any) => result?.[0]?.transcript ?? '')
          .join(' ')
          .trim();
        setLiveTranscript(text);
        liveTranscriptRef.current = text;
      };
      recognitionRef.current = recognition;
    }

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunksRef.current.push(e.data);
      }
    };

    recorder.onstop = () => {
      stopRecognition();
      const blob = new Blob(audioChunksRef.current, { type: mimeType || 'audio/webm' });
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      const transcriptText = liveTranscriptRef.current.trim();
      sendAudioToBackend(blob, transcriptText || undefined);
    };

    recorder.start(100);
    if (recognitionRef.current) {
      try {
        recognitionRef.current.start();
      } catch {
        // no-op
      }
    }
    setIsListening(true);
  }, [isListening, isProcessing, language.code, sendAudioToBackend, stopRecognition]);

  const handleBack = useCallback(() => {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    setIsSpeaking(false);
    cleanupRecording();
    onBack();
  }, [onBack, cleanupRecording]);

  return (
    <div className="min-h-screen bg-black flex flex-col relative">
      <div className="relative z-10 flex items-center justify-between px-6 py-4">
        <BackButton onClick={handleBack} label={backLabel} />
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-full border bg-[#111111] font-body text-sm font-medium"
          style={{ borderColor: `${accent}40`, color: accent }}
        >
          {language.nativeName}
        </div>
      </div>

      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 -mt-8">
        <MicButton
          isListening={isListening}
          isProcessing={isProcessing}
          isSpeaking={isSpeaking}
          onClick={handleMicClick}
        />

        <div className="mt-10 text-center min-h-[80px]">
          {errorMsg ? (
            <p className="text-base md:text-lg text-red-400 font-body max-w-sm">{errorMsg}</p>
          ) : isProcessing ? (
            <p className="text-2xl md:text-3xl font-heading font-semibold text-[#f59e0b]">Processing...</p>
          ) : (
            <p
              className={`text-2xl md:text-3xl font-heading font-semibold transition-colors duration-300 ${
                isListening ? 'text-[#f59e0b]' : 'text-[#9ca3af]'
              }`}
            >
              {isListening ? prompt.hint : prompt.speak}
            </p>
          )}
        </div>

        {isListening && liveTranscript && (
          <div className="mt-4 text-gray-300 text-center text-lg">
            {liveTranscript}
          </div>
        )}
      </div>

      <div className="relative z-10 py-6 text-center">
        <p className="text-[#555555] text-sm font-body">{hintText}</p>
      </div>
    </div>
  );
};

export default VoiceInteraction;
