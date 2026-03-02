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

const cardAccents: Record<string, string> = {
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

const languages: Language[] = [
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', greeting: 'नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?' },
  { code: 'en', name: 'English', nativeName: 'English', greeting: 'Hello, how can I help you?' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी', greeting: 'नमस्कार, मी तुम्हाला कशी मदत करू?' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', greeting: 'নমস্কার, আমি আপনাকে কীভাবে সাহায্য করতে পারি?' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', greeting: 'வணக்கம், நான் உங்களுக்கு எப்படி உதவலாம்?' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', greeting: 'నమస్కారం, నేను మీకు ఎలా సహాయం చేయగలను?' },
  { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ', greeting: 'ನಮಸ್ಕಾರ, ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?' },
  { code: 'ml', name: 'Malayalam', nativeName: 'മലയാളം', greeting: 'നമസ്കാരം, ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?' },
  { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', greeting: 'ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?' },
  { code: 'gu', name: 'Gujarati', nativeName: 'ગુજરાતી', greeting: 'નમસ્તે, હું તમને કેવી રીતે મદદ કરી શકું?' },
];

const LanguageSelector = ({ onSelectLanguage }: LanguageSelectorProps) => {
  const [hoveredLang, setHoveredLang] = useState<string | null>(null);

  const handleClick = useCallback(
    (lang: Language) => {
      onSelectLanguage(lang);
    },
    [onSelectLanguage]
  );

  return (
    <section className="relative z-10 w-full max-w-5xl mx-auto px-4 sm:px-6 py-10">
      {/* Section heading */}
      <div className="text-center mb-8">
        <h2 className="text-3xl md:text-4xl font-heading font-bold text-[#f5f5f5]">
          Choose Your Language
        </h2>
        <p className="mt-2 text-lg text-[#9ca3af] font-script">
          अपनी भाषा चुनें
        </p>
      </div>

      {/* Language card grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
        {languages.map((lang, index) => {
          const accent = cardAccents[lang.code] || '#9ca3af';
          const isHovered = hoveredLang === lang.code;

          return (
            <button
              key={lang.code}
              onClick={() => handleClick(lang)}
              onMouseEnter={() => setHoveredLang(lang.code)}
              onMouseLeave={() => setHoveredLang(null)}
              className="relative overflow-hidden rounded-xl bg-[#111111] border border-[#2a2a2a] flex flex-col items-center justify-center p-5 cursor-pointer transition-all duration-300 ease-out opacity-0 animate-fade-in hover:-translate-y-1"
              style={{
                animationDelay: `${index * 0.06}s`,
                borderColor: isHovered ? `${accent}50` : '#2a2a2a',
                boxShadow: isHovered ? `0 8px 24px rgba(0,0,0,0.4)` : '0 2px 8px rgba(0,0,0,0.2)',
              }}
            >
              {/* Colored top border */}
              <div
                className="absolute top-0 left-0 right-0 h-1 transition-opacity duration-300"
                style={{ backgroundColor: accent, opacity: isHovered ? 1 : 0.6 }}
              />

              {/* Mic icon */}
              <div
                className="mb-3 p-2.5 rounded-full transition-colors duration-300"
                style={{
                  backgroundColor: isHovered ? `${accent}15` : '#1a1a1a',
                }}
              >
                <Mic
                  className="w-5 h-5 transition-colors duration-300"
                  style={{ color: isHovered ? accent : '#9ca3af' }}
                />
              </div>

              {/* Native name */}
              <span className="text-xl md:text-2xl font-semibold text-[#f5f5f5] font-script mb-1">
                {lang.nativeName}
              </span>

              {/* English name */}
              <span className="text-xs text-[#9ca3af] font-body tracking-wide uppercase">
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
