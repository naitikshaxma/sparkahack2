import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import MicButton from './MicButton';
import BackButton from './BackButton';
import { speakText, micHints } from '@/lib/voiceUtils';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

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
  hi: { speak: 'बोलिए...', hint: 'मैं सुन रहा हूं' },
  en: { speak: 'Speak now...', hint: 'I am listening' },
  mr: { speak: 'बोला...', hint: 'मी ऐकतो आहे' },
  bn: { speak: 'বলুন...', hint: 'আমি শুনছি' },
  ta: { speak: 'பேசுங்கள்...', hint: 'நான் கேட்கிறேன்' },
  te: { speak: 'చెప్పండి...', hint: 'నేను వింటున్నాను' },
  kn: { speak: 'ಹೇಳಿ...', hint: 'ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ' },
  ml: { speak: 'പറയൂ...', hint: 'ഞാൻ കേൾക്കുന്നു' },
  pa: { speak: 'ਬੋਲੋ...', hint: 'ਮੈਂ ਸੁਣ ਰਿਹਾ ਹਾਂ' },
  gu: { speak: 'બોલો...', hint: 'હું સાંભળી રહ્યો છું' },
};

const backLabels: Record<string, string> = {
  hi: 'भाषा बदलें', en: 'Change language', mr: 'भाषा बदला',
  bn: 'ভাষা পরিবর্তন করুন', ta: 'மொழியை மாற்றவும்', te: 'భాష మార్చండి',
  kn: 'ಭಾಷೆ ಬದಲಾಯಿಸಿ', ml: 'ഭാഷ മാറ്റുക', pa: 'ਭਾਸ਼ਾ ਬਦਲੋ', gu: 'ભાષા બદલો',
};

const langAccents: Record<string, string> = {
  hi: '#f59e0b', en: '#9ca3af', mr: '#ea580c', bn: '#dc2626', ta: '#14b8a6',
  te: '#b91c1c', kn: '#16a34a', ml: '#7c3aed', pa: '#d97706', gu: '#2563eb',
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

const VoiceInteraction = ({ language, onBack }: VoiceInteractionProps) => {
  const navigate = useNavigate();
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const hasGreetedRef = useRef(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const prompt = prompts[language.code] ?? prompts.en;
  const backLabel = backLabels[language.code] ?? backLabels.en;
  const accent = langAccents[language.code] ?? '#f59e0b';
  const hintText = micHints[language.code] ?? micHints.en;

  /* Cancel everything on unmount */
  const cleanupRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
  }, []);

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
        () => { if (!cancelled) setIsSpeaking(true); },
        () => { if (!cancelled) setIsSpeaking(false); },
        () => { if (!cancelled) setIsSpeaking(false); },
      );
    };

    const voices = speechSynthesis.getVoices();
    if (voices.length > 0) {
      setTimeout(() => doSpeak(voices), 200);
    } else {
      const handler = () => {
        const v = speechSynthesis.getVoices();
        if (v.length > 0) {
          doSpeak(v);
          speechSynthesis.removeEventListener('voiceschanged', handler);
        }
      };
      speechSynthesis.addEventListener('voiceschanged', handler);
      setTimeout(() => { if (!hasGreetedRef.current) doSpeak(speechSynthesis.getVoices()); }, 1000);
    }

    return () => {
      cancelled = true;
      speechSynthesis.cancel();
      cleanupRecording();
    };
  }, [language, cleanupRecording]);

  /** POST recorded audio blob to backend and navigate to result */
  const sendAudioToBackend = useCallback(async (audioBlob: Blob) => {
    setIsProcessing(true);
    setErrorMsg('');

    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
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
    } catch (err) {
      console.warn('Backend unavailable. Using mock response for frontend testing.', err);
      // Simulate backend response for frontend-only testing
      navigate('/result', {
        state: {
          language: language.name,
          languageCode: language.code,
          transcript: "This is a simulated transcript because the backend is not running.",
          intent: "mock_intent_success",
          confidence: 99,
          response_text: "Since this is a frontend-only repository, this is a simulated response indicating your audio was processed.",
          audio_base64: "", // No audio explicitly mapped for mock
        },
      });
      setIsProcessing(false);
    }
  }, [language, navigate]);

  /** Start or stop recording */
  const handleMicClick = useCallback(async () => {
    if (isProcessing) return;

    // STOP recording
    if (isListening) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop(); // triggers onstop → sendAudioToBackend
      }
      setIsListening(false);
      return;
    }

    // Cancel any ongoing speech synthesis
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    setIsSpeaking(false);
    setErrorMsg('');

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

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunksRef.current.push(e.data);
      }
    };

    recorder.onstop = () => {
      const blob = new Blob(audioChunksRef.current, { type: mimeType || 'audio/webm' });
      // Stop all mic tracks
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      sendAudioToBackend(blob);
    };

    recorder.start(100); // collect chunks every 100 ms
    setIsListening(true);
  }, [isListening, isProcessing, sendAudioToBackend]);

  const handleBack = useCallback(() => {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    setIsSpeaking(false);
    cleanupRecording();
    onBack();
  }, [onBack, cleanupRecording]);

  return (
    <div className="min-h-screen bg-black flex flex-col relative">
      {/* Top bar */}
      <div className="relative z-10 flex items-center justify-between px-6 py-4">
        <BackButton onClick={handleBack} label={backLabel} />
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-full border bg-[#111111] font-body text-sm font-medium"
          style={{ borderColor: `${accent}40`, color: accent }}
        >
          {language.nativeName}
        </div>
      </div>

      {/* Main content */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 -mt-8">
        <MicButton
          isListening={isListening}
          isProcessing={isProcessing}
          isSpeaking={isSpeaking}
          onClick={handleMicClick}
        />

        {/* Status text */}
        <div className="mt-10 text-center min-h-[80px]">
          {errorMsg ? (
            <p className="text-base md:text-lg text-red-400 font-body max-w-sm">{errorMsg}</p>
          ) : isProcessing ? (
            <p className="text-2xl md:text-3xl font-heading font-semibold text-[#f59e0b]">
              Processing...
            </p>
          ) : (
            <p className={`text-2xl md:text-3xl font-heading font-semibold transition-colors duration-300 ${
              isListening ? 'text-[#f59e0b]' : 'text-[#9ca3af]'
            }`}>
              {isListening ? prompt.hint : prompt.speak}
            </p>
          )}
        </div>
      </div>

      {/* Bottom hint */}
      <div className="relative z-10 py-6 text-center">
        <p className="text-[#555555] text-sm font-body">{hintText}</p>
      </div>
    </div>
  );
};

export default VoiceInteraction;
