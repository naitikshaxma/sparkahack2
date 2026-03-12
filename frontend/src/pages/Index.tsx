import { useState, useCallback } from 'react';
import SparkleBackground from '@/components/result/SparkleBackground';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import LanguageSelector from '@/components/LanguageSelector';
import VoiceInteraction from '@/components/VoiceInteraction';

type AppStage = 'landing' | 'voice';

interface Language {
  code: string;
  name: string;
  nativeName: string;
  greeting: string;
}

const Index = () => {
  const [stage, setStage] = useState<AppStage>('landing');
  const [selectedLanguage, setSelectedLanguage] = useState<Language | null>(null);

  const handleLanguageSelect = useCallback((language: Language) => {
    setSelectedLanguage(language);
    setStage('voice');
  }, []);

  const handleBackToLanding = useCallback(() => {
    setStage('landing');
  }, []);

  /* Voice interaction — full screen with dark bg */
  if (stage === 'voice' && selectedLanguage) {
    return (
      <>
        <SparkleBackground />
        <VoiceInteraction
          language={selectedLanguage}
          onBack={handleBackToLanding}
        />
      </>
    );
  }

  /* Landing page — dark theme with sparkle */
  return (
    <div className="min-h-screen relative">
      <SparkleBackground />

      <div className="relative z-10 min-h-screen flex flex-col">
        <Navbar />

        {/* Hero section */}
        <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 pt-10 pb-2 text-center">
          <p className="text-sm font-body font-medium text-[#14b8a6] uppercase tracking-widest mb-3 opacity-0 animate-fade-in">
            Multilingual Voice Assistant
          </p>
          <h1 className="text-4xl md:text-5xl font-heading font-bold text-[#f5f5f5] leading-tight opacity-0 animate-fade-in" style={{ animationDelay: '0.1s' }}>
            Speak in your language.
            <br />
            <span className="text-[#f59e0b]">We understand.</span>
          </h1>
          <p className="mt-4 text-base md:text-lg text-[#9ca3af] font-body max-w-xl mx-auto opacity-0 animate-fade-in" style={{ animationDelay: '0.2s' }}>
            Voice OS brings AI-powered voice assistance to every Indian citizen,
            in the language they speak best.
          </p>
        </div>

        {/* Language selector */}
        <LanguageSelector onSelectLanguage={handleLanguageSelect} />

        {/* About section */}
        <section className="relative z-10 w-full max-w-4xl mx-auto px-6 py-10">
          <div className="bg-[#111111] rounded-xl border border-[#2a2a2a] p-6 md:p-8">
            <h3 className="text-xl font-heading font-bold text-[#f5f5f5] mb-3">
              About Voice OS
            </h3>
            <p className="text-[#9ca3af] font-body text-sm leading-relaxed">
              Voice OS Bharat is a multilingual AI voice assistant built for Bharat.
              It supports 10 Indian languages including Hindi, Tamil, Bengali, Telugu, and more.
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
