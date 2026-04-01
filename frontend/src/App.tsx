import { useState, useCallback } from 'react';
import { BrowserRouter, Routes, Route, useSearchParams } from 'react-router-dom';
import IntroScreen from './components/IntroScreen';
import Index from './pages/Index';
import ResultPage from './pages/ResultPage';
import NotFound from './pages/NotFound';
import DemoForm from './pages/DemoForm';
import VoiceInteraction from './components/VoiceInteraction';

/* --------------------------------------------------------------------------
   Language data — same list used in LanguageSelector, duplicated here so the
   /assistant?lang=hi route can resolve the full Language object from the code.
-------------------------------------------------------------------------- */
const LANGUAGES = [
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

/** /assistant?lang=hi — direct route for spec compliance */
const AssistantRoute = () => {
  const [params] = useSearchParams();
  const langCode = params.get('lang') ?? localStorage.getItem('voice_os_language') ?? localStorage.getItem('language') ?? 'en';
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
        <Route path="/demo-form" element={<DemoForm />} />
        <Route path="/result" element={<ResultPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
