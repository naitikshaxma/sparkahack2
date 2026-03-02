import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import MicButton from './MicButton';
import BackButton from './BackButton';

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

/* --- Voice matching helpers --- */
const langVoiceTags: Record<string, string[]> = {
  hi: ['hi-IN', 'hi'], en: ['en-IN', 'en-US', 'en-GB', 'en'],
  mr: ['mr-IN', 'mr'], bn: ['bn-IN', 'bn-BD', 'bn'],
  ta: ['ta-IN', 'ta'], te: ['te-IN', 'te'],
  kn: ['kn-IN', 'kn'], ml: ['ml-IN', 'ml'],
  pa: ['pa-IN', 'pa-Guru-IN', 'pa'], gu: ['gu-IN', 'gu'],
};

const langSearchNames: Record<string, string[]> = {
  hi: ['hindi', 'हिन्दी', 'swara'], en: ['english', 'heera'],
  mr: ['marathi'], bn: ['bengali', 'bangla'],
  ta: ['tamil'], te: ['telugu'],
  kn: ['kannada'], ml: ['malayalam'],
  pa: ['punjabi', 'panjabi'], gu: ['gujarati'],
};

function findVoice(voices: SpeechSynthesisVoice[], langCode: string): SpeechSynthesisVoice | null {
  const tags = langVoiceTags[langCode] || [`${langCode}-IN`, langCode];
  const localVoices = voices.filter((v) => v.localService);
  const remoteVoices = voices.filter((v) => !v.localService);
  for (const voiceSet of [localVoices, remoteVoices]) {
    for (const tag of tags) { const v = voiceSet.find((v) => v.lang === tag); if (v) return v; }
    for (const tag of tags) { const v = voiceSet.find((v) => v.lang.startsWith(tag)); if (v) return v; }
    const names = langSearchNames[langCode] || [];
    for (const name of names) { const v = voiceSet.find((v) => v.name.toLowerCase().includes(name.toLowerCase())); if (v) return v; }
  }
  return null;
}

function speakText(text: string, langCode: string, voices: SpeechSynthesisVoice[],
  onStart?: () => void, onEnd?: () => void, onError?: () => void): void {
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const voice = findVoice(voices, langCode);
  if (voice) { utterance.voice = voice; utterance.lang = voice.lang; }
  else { utterance.lang = langCode === 'en' ? 'en-IN' : `${langCode}-IN`; }
  utterance.rate = 0.9; utterance.pitch = 1; utterance.volume = 1;
  if (onStart) utterance.onstart = onStart;
  if (onEnd) utterance.onend = onEnd;
  if (onError) utterance.onerror = onError;
  speechSynthesis.speak(utterance);
  setTimeout(() => { if (speechSynthesis.paused) speechSynthesis.resume(); }, 150);
}

const VoiceInteraction = ({ language, onBack }: VoiceInteractionProps) => {
  const navigate = useNavigate();
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcript, setTranscript] = useState('');
  const hasGreetedRef = useRef(false);
  const transcriptRef = useRef('');

  const prompt = prompts[language.code] || prompts.en;
  const backLabel = backLabels[language.code] || backLabels.en;
  const accent = langAccents[language.code] || '#f59e0b';

  const handleBack = useCallback(() => {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    setIsSpeaking(false);
    onBack();
  }, [onBack]);

  /* Speak greeting on mount */
  useEffect(() => {
    if (!('speechSynthesis' in window)) return;
    if (hasGreetedRef.current) return;
    let cancelled = false;

    const doSpeak = (voices: SpeechSynthesisVoice[]) => {
      if (cancelled || hasGreetedRef.current) return;
      hasGreetedRef.current = true;
      speakText(language.greeting, language.code, voices,
        () => { if (!cancelled) setIsSpeaking(true); },
        () => { if (!cancelled) setIsSpeaking(false); },
        () => { if (!cancelled) setIsSpeaking(false); }
      );
    };

    const voices = speechSynthesis.getVoices();
    if (voices.length > 0) { setTimeout(() => doSpeak(voices), 200); }
    else {
      const handler = () => { const v = speechSynthesis.getVoices(); if (v.length > 0) { doSpeak(v); speechSynthesis.removeEventListener('voiceschanged', handler); } };
      speechSynthesis.addEventListener('voiceschanged', handler);
      setTimeout(() => { if (!hasGreetedRef.current) doSpeak(speechSynthesis.getVoices()); }, 1000);
    }
    return () => { cancelled = true; speechSynthesis.cancel(); };
  }, [language]);

  /* Navigate to result page after speech recognition completes */
  const navigateToResult = useCallback((spokenText: string) => {
    navigate('/result', {
      state: {
        language: language.name,
        languageCode: language.code,
        transcript: spokenText,
      },
    });
  }, [navigate, language]);

  /* Fallback transcripts when Chrome can't capture speech in that language */
  const fallbackTranscripts: Record<string, string> = {
    hi: 'मेरा खाता बैलेंस बताइए',
    en: 'Check my account balance',
    mr: 'माझ्या खात्यातील शिल्लक सांगा',
    bn: 'আমার অ্যাকাউন্ট ব্যালেন্স জানান',
    ta: 'என் கணக்கு இருப்பை சொல்லுங்கள்',
    te: 'నా ఖాతా బ్యాలెన్స్ చెప్పండి',
    kn: 'ನನ್ನ ಖಾತೆ ಬ್ಯಾಲೆನ್ಸ್ ಹೇಳಿ',
    ml: 'എന്റെ അക്കൗണ്ട് ബാലൻസ് പറയൂ',
    pa: 'ਮੇਰਾ ਖਾਤਾ ਬੈਲੈਂਸ ਦੱਸੋ',
    gu: 'મારું ખાતું બેલેન્સ જણાવો',
  };

  const handleMicClick = useCallback(() => {
    if (isListening) { setIsListening(false); return; }
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      // No speech recognition available — navigate directly with fallback
      setIsProcessing(true);
      setTimeout(() => navigateToResult(fallbackTranscripts[language.code] || 'Voice input received'), 1200);
      return;
    }

    // Cancel any ongoing speech
    speechSynthesis.cancel();
    setIsSpeaking(false);

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = language.code === 'en' ? 'en-IN' : `${language.code}-IN`;
    recognition.continuous = false;
    recognition.interimResults = true;
    let hasNavigated = false;

    const doNavigate = () => {
      if (hasNavigated) return;
      hasNavigated = true;
      setIsListening(false);
      setIsProcessing(true);
      const finalText = transcriptRef.current || fallbackTranscripts[language.code] || 'Voice input received';
      setTimeout(() => navigateToResult(finalText), 1200);
    };

    recognition.onstart = () => { setIsListening(true); setTranscript(''); transcriptRef.current = ''; };
    recognition.onresult = (event: any) => {
      const text = event.results[event.resultIndex][0].transcript;
      setTranscript(text);
      transcriptRef.current = text;
    };
    recognition.onend = () => {
      // Always navigate — use fallback if no transcript captured
      doNavigate();
    };
    recognition.onerror = (event: any) => {
      // Navigate even on error (no-speech, audio-capture, etc.)
      console.log('Speech recognition error:', event.error);
      doNavigate();
    };
    recognition.start();
  }, [isListening, language.code, navigateToResult]);

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
          {transcript ? (
            <p className="text-xl md:text-2xl text-[#f5f5f5] font-body max-w-md">
              "{transcript}"
            </p>
          ) : isProcessing ? (
            <p className="text-2xl md:text-3xl font-heading font-semibold text-[#f59e0b]">
              Processing...
            </p>
          ) : (
            <p className={`text-2xl md:text-3xl font-heading font-semibold transition-colors duration-300 ${isListening ? 'text-[#f59e0b]' : 'text-[#9ca3af]'
              }`}>
              {isListening ? prompt.hint : prompt.speak}
            </p>
          )}
        </div>
      </div>

      {/* Bottom hint */}
      <div className="relative z-10 py-6 text-center">
        <p className="text-[#555555] text-sm font-body">
          {language.code === 'hi'
            ? 'माइक बटन दबाएं और बोलें'
            : 'Tap the microphone and speak'}
        </p>
      </div>
    </div>
  );
};

export default VoiceInteraction;
