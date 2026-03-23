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
  { code: 'hi', name: 'Hindi',     nativeName: 'हिन्दी',    greeting: 'नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?' },
  { code: 'en', name: 'English',   nativeName: 'English',   greeting: 'Hello, how can I help you?' },
];

/** /assistant?lang=hi — direct route for spec compliance */
const AssistantRoute = () => {
  const [params] = useSearchParams();
  const langCode = params.get('lang') ?? localStorage.getItem('language') ?? 'en';
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
