import { useState, useCallback } from 'react';
import LanguageSelector from '@/components/LanguageSelector';
import AudioRecorder from '@/components/AudioRecorder';

type AppStage = 'landing' | 'voice';

interface Language {
    code: string;
    name: string;
    nativeName: string;
    greeting: string;
}

const Home = () => {
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
            <AudioRecorder
                language={selectedLanguage}
                onBack={handleBackToLanding}
            />
        );
    }

    /* Landing page — dark theme */
    return (
        <div className="min-h-screen relative bg-black">
            <div className="relative z-10 min-h-screen flex flex-col">
                {/* Navbar */}
                <nav className="relative z-10 w-full px-6 py-4 border-b border-[#2a2a2a]">
                    <div className="max-w-7xl mx-auto flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-[#f59e0b] flex items-center justify-center">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                                    <line x1="12" x2="12" y1="19" y2="22" />
                                </svg>
                            </div>
                            <span className="text-[#f5f5f5] font-heading font-semibold text-base tracking-tight">
                                Voice OS <span className="text-[#f59e0b]">Bharat</span>
                            </span>
                        </div>
                        <span className="text-[#9ca3af] text-sm font-body hidden sm:block">
                            Multilingual Voice Assistant
                        </span>
                    </div>
                </nav>

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

                {/* Footer */}
                <footer className="relative z-10 w-full py-6 text-center border-t border-[#2a2a2a] mt-auto">
                    <p className="text-sm font-body text-[#555555]">
                        Voice OS Bharat — Made for India
                    </p>
                </footer>
            </div>
        </div>
    );
};

export default Home;
