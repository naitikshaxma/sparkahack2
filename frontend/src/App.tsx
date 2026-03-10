import { useState, useCallback } from 'react';
import { BrowserRouter, Routes, Route, useSearchParams } from 'react-router-dom';
import IntroScreen from './components/IntroScreen';
import Index from './pages/Index';
import ResultPage from './pages/ResultPage';
import NotFound from './pages/NotFound';
import VoiceInteraction from './components/VoiceInteraction';

/* --------------------------------------------------------------------------
   Language data — same list used in LanguageSelector, duplicated here so the
   /assistant?lang=hi route can resolve the full Language object from the code.
-------------------------------------------------------------------------- */
const LANGUAGES = [
  { code: 'hi', name: 'Hindi',     nativeName: 'हिन्दी',    greeting: 'नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?' },
  { code: 'en', name: 'English',   nativeName: 'English',   greeting: 'Hello, how can I help you?' },
  { code: 'mr', name: 'Marathi',   nativeName: 'मराठी',     greeting: 'नमस्कार, मी तुम्हाला कशी मदत करू?' },
  { code: 'bn', name: 'Bengali',   nativeName: 'বাংলা',     greeting: 'নমস্কার, আমি আপনাকে কীভাবে সাহায্য করতে পারি?' },
  { code: 'ta', name: 'Tamil',     nativeName: 'தமிழ்',    greeting: 'வணக்கம், நான் உங்களுக்கு எப்படி உதவலாம்?' },
  { code: 'te', name: 'Telugu',    nativeName: 'తెలుగు',   greeting: 'నమస్కారం, నేను మీకు ఎలా సహాయం చేయగలను?' },
  { code: 'kn', name: 'Kannada',   nativeName: 'ಕನ್ನಡ',   greeting: 'ನಮಸ್ಕಾರ, ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?' },
  { code: 'ml', name: 'Malayalam', nativeName: 'മലയാളം',  greeting: 'നമസ്കാരം, ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?' },
  { code: 'pa', name: 'Punjabi',   nativeName: 'ਪੰਜਾਬੀ',  greeting: 'ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?' },
  { code: 'gu', name: 'Gujarati',  nativeName: 'ગુજરાતી', greeting: 'નમસ્તે, હું તમને કેવી રીતે મદદ કરી શકું?' },
];

/** /assistant?lang=hi — direct route for spec compliance */
const AssistantRoute = () => {
  const [params] = useSearchParams();
  const langCode = params.get('lang') ?? 'en';
  const language = LANGUAGES.find((l) => l.code === langCode) ?? LANGUAGES[1];

  const handleBack = useCallback(() => {
    window.history.back();
  }, []);

  return <VoiceInteraction language={language} onBack={handleBack} />;
};

const App = () => {
  const [showIntro, setShowIntro] = useState(true);

  const handleIntroComplete = useCallback(() => {
    setShowIntro(false);
  }, []);

  if (showIntro) {
    return <IntroScreen onComplete={handleIntroComplete} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Index />} />
        <Route path="/assistant" element={<AssistantRoute />} />
        <Route path="/result" element={<ResultPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
