import { useState, useCallback, useEffect } from 'react';
import SparkleBackground from '@/components/SparkleBackground';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import LanguageSelector from '@/components/LanguageSelector';
import VoiceInteraction from '@/components/VoiceInteraction';
import AuthScreen from '@/components/AuthScreen';
import ScreenErrorBoundary from '@/components/ScreenErrorBoundary';

type AppStage = 'auth' | 'language' | 'voice';
type StoredUser = { name: string; phone: string };

const USER_STORAGE_KEY = 'voice_os_user';
const PHONE_STORAGE_KEY = 'voice_os_user_phone';

const readStoredUser = (): StoredUser | null => {
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as StoredUser;
    if (typeof parsed?.name === 'string' && typeof parsed?.phone === 'string') {
      return parsed;
    }
  } catch {
    return null;
  }
  return null;
};

interface Language {
  code: string;
  name: string;
  nativeName: string;
  greeting: string;
}

const LANGUAGES: Language[] = [
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

const Index = () => {
  const [stage, setStage] = useState<AppStage>('auth');
  const [selectedLanguage, setSelectedLanguage] = useState<Language | null>(() => {
    const stored = localStorage.getItem('voice_os_language') || localStorage.getItem('language') || '';
    return LANGUAGES.find((lang) => lang.code === stored) ?? null;
  });

  useEffect(() => {
    const storedUser = readStoredUser();
    if (storedUser?.phone) {
      localStorage.setItem(PHONE_STORAGE_KEY, storedUser.phone);
    }
  }, []);

  const handleAuthSuccess = useCallback((user: StoredUser) => {
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    localStorage.setItem(PHONE_STORAGE_KEY, user.phone);
    setStage('language');
  }, []);

  const handleLanguageSelect = useCallback((language: Language) => {
    localStorage.setItem('voice_os_language', language.code);
    localStorage.setItem('language', language.code);
    setSelectedLanguage(language);
    setStage('voice');
  }, []);

  const handleBackToLanguage = useCallback(() => {
    setStage('language');
  }, []);

  useEffect(() => {
    if (stage !== 'voice' || selectedLanguage) {
      return;
    }
    const stored = localStorage.getItem('voice_os_language') || localStorage.getItem('language') || '';
    const resolved = LANGUAGES.find((lang) => lang.code === stored) ?? LANGUAGES[1];
    setSelectedLanguage(resolved);
  }, [stage, selectedLanguage]);

  /* Voice interaction — full screen with dark bg */
  if (stage === 'voice' && selectedLanguage) {
    return (
      <ScreenErrorBoundary onRecover={handleBackToLanguage}>
        <VoiceInteraction
          language={selectedLanguage}
          onBack={handleBackToLanguage}
        />
      </ScreenErrorBoundary>
    );
  }

  if (stage === 'auth') {
    return <AuthScreen onAuthenticated={handleAuthSuccess} />;
  }

  /* Landing page — dark theme with sparkle */
  return (
    <div className="relative min-h-screen bg-black">
      <SparkleBackground />

      <div className="relative z-10 min-h-screen flex flex-col">
        <Navbar />

        {/* Hero section */}
        <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 pt-10 pb-2 text-center">
          <p className="text-sm font-body font-medium text-[#f59e0b] uppercase tracking-widest mb-3 opacity-0 animate-fade-in">
            Bilingual Voice Assistant
          </p>
          <h1 className="text-4xl md:text-5xl font-heading font-bold text-white leading-tight opacity-0 animate-fade-in" style={{ animationDelay: '0.1s' }}>
            Speak in your language.
            <br />
            <span className="text-[#f59e0b]">We understand.</span>
          </h1>
          <p className="mt-4 text-base md:text-lg text-gray-400 font-body max-w-xl mx-auto opacity-0 animate-fade-in" style={{ animationDelay: '0.2s' }}>
            Voice OS brings AI-powered voice assistance to every Indian citizen,
            in the language they speak best.
          </p>
        </div>

        {/* Language selector */}
        <LanguageSelector onSelectLanguage={handleLanguageSelect} />


        {/* About section */}
        <section className="relative z-10 w-full max-w-4xl mx-auto px-6 py-10">
          <div className="bg-[#0f0f0f] rounded-2xl border border-white/10 p-6 md:p-8">
            <h3 className="text-xl font-heading font-bold text-white mb-3">
              About Voice OS
            </h3>
            <p className="text-gray-400 font-body text-sm leading-relaxed">
              Voice OS Bharat is a multilingual AI voice assistant built for Bharat.
              It supports multiple Indian languages.
              Simply select your language and start speaking — the assistant will listen,
              understand, and respond in your preferred language.
            </p>
          </div>
        </section>

        <Footer />
      </div>
    </div>
  );
};

export default Index;
