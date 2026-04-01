import { useState, useCallback } from 'react';
import { Mic } from 'lucide-react';

interface Language {
  code: string;
  name: string;
  nativeName: string;
  greeting: string;
}

interface LanguageSelectorProps {
  onSelectLanguage: (language: Language) => void;
}

const defaultAccent = '#f59e0b';
const cardAccents: Record<string, string> = {
  hi: '#f59e0b',
  en: '#fbbf24',
  bn: '#f97316',
  pa: '#f43f5e',
  ta: '#84cc16',
  te: '#22c55e',
  mr: '#10b981',
  gu: '#14b8a6',
  kn: '#eab308',
  ur: '#f472b6',
};

const languages: Language[] = [
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', greeting: 'Namaste, main aapki madad kaise kar sakta hoon?' },
  { code: 'en', name: 'English', nativeName: 'English', greeting: 'Hello, how can I help you?' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', greeting: 'নমস্কার, আমি কীভাবে সাহায্য করতে পারি?' },
  { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', greeting: 'ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਤੁਹਾਡੀ ਮਦਦ ਕਿਵੇਂ ਕਰ ਸਕਦਾ ਹਾਂ?' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', greeting: 'வணக்கம், நான் எப்படி உதவ முடியும்?' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', greeting: 'నమస్తే, నేను ఎలా సహాయం చేయగలను?' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी', greeting: 'नमस्कार, मी कशी मदत करू?' },
  { code: 'gu', name: 'Gujarati', nativeName: 'ગુજરાતી', greeting: 'નમસ્તે, હું કેવી રીતે મદદ કરી શકું?' },
  { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ', greeting: 'ನಮಸ್ಕಾರ, ನಾನು ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?' },
  { code: 'ur', name: 'Urdu', nativeName: 'اردو', greeting: 'السلام علیکم، میں آپ کی کیسے مدد کر سکتا ہوں؟' },
];

const LANGUAGE_STORAGE_KEY = "voice_os_language";
const LEGACY_LANGUAGE_KEY = "language";
const speechLangMap: Record<string, string> = {
  hi: "hi-IN",
  en: "en-US",
  bn: "bn-IN",
  pa: "pa-IN",
  ta: "ta-IN",
  te: "te-IN",
  mr: "mr-IN",
  gu: "gu-IN",
  kn: "kn-IN",
  ur: "ur-IN",
};

const LanguageSelector = ({ onSelectLanguage }: LanguageSelectorProps) => {
  const [hoveredLang, setHoveredLang] = useState<string | null>(null);

  const handleClick = useCallback(
    (lang: Language) => {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, lang.code);
      localStorage.setItem(LEGACY_LANGUAGE_KEY, lang.code);
      try {
        if ("speechSynthesis" in window) {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(lang.greeting);
          utterance.lang = speechLangMap[lang.code] || "en-US";
          window.speechSynthesis.speak(utterance);
        }
      } catch {
      }
      onSelectLanguage(lang);
    },
    [onSelectLanguage]
  );

  return (
    <section className="relative z-10 w-full max-w-6xl mx-auto px-4 sm:px-6 py-10">
      {/* Section heading */}
      <div className="text-center mb-8">
        <h2 className="text-3xl md:text-4xl font-heading font-bold text-white">
          Choose Your Language
        </h2>
        <p className="mt-2 text-lg text-gray-400 font-script">
          अपनी भाषा चुनें
        </p>
      </div>

      {/* Language card grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 max-w-6xl mx-auto">
        {languages.map((lang, index) => {
          const accent = cardAccents[lang.code] || defaultAccent;
          const isHovered = hoveredLang === lang.code;

          return (
            <button
              key={lang.code}
              onClick={() => handleClick(lang)}
              onMouseEnter={() => setHoveredLang(lang.code)}
              onMouseLeave={() => setHoveredLang(null)}
              className="relative w-full overflow-hidden rounded-2xl bg-[#0f0f0f] border border-white/10 flex flex-col items-center justify-center p-5 cursor-pointer transition-all duration-300 ease-out opacity-0 animate-fade-in hover:-translate-y-1 hover:bg-white/10"
              style={{
                animationDelay: `${index * 0.06}s`,
                borderColor: isHovered ? `${accent}80` : `${accent}55`,
                boxShadow: isHovered
                  ? `0 10px 28px rgba(0,0,0,0.45), 0 0 18px ${accent}40`
                  : `0 2px 8px rgba(0,0,0,0.2), 0 0 12px ${accent}20`,
              }}
            >
              {/* Colored top border */}
              <div
                className="absolute top-0 left-0 right-0 h-1 transition-opacity duration-300"
                style={{ backgroundColor: accent, opacity: isHovered ? 1 : 0.85, boxShadow: `0 0 14px ${accent}55` }}
              />

              {/* Mic icon */}
              <div
                className="mb-3 p-2.5 rounded-full transition-colors duration-300"
                style={{
                  backgroundColor: isHovered ? `${accent}20` : 'rgba(255,255,255,0.06)',
                }}
              >
                <Mic
                  className="w-5 h-5 transition-colors duration-300"
                  style={{ color: isHovered ? accent : '#9ca3af' }}
                />
              </div>

              {/* Native name */}
              <span className="text-xl md:text-2xl font-semibold text-white font-script mb-1">
                {lang.nativeName}
              </span>

              {/* English name */}
              <span className="text-xs text-gray-400 font-body tracking-wide uppercase">
                {lang.name}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
};

export default LanguageSelector;
