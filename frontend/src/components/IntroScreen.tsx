import { useState, useEffect } from 'react';
import SparkleBackground from './result/SparkleBackground';

const languages = [
    { native: 'हिन्दी', english: 'HINDI' },
    { native: 'English', english: 'ENGLISH' },
    { native: 'मराठी', english: 'MARATHI' },
    { native: 'বাংলা', english: 'BENGALI' },
    { native: 'தமிழ்', english: 'TAMIL' },
    { native: 'తెలుగు', english: 'TELUGU' },
    { native: 'ಕನ್ನಡ', english: 'KANNADA' },
    { native: 'മലയാളം', english: 'MALAYALAM' },
    { native: 'ਪੰਜਾਬੀ', english: 'PUNJABI' },
    { native: 'ગુજરાતી', english: 'GUJARATI' },
];

const INTERVAL_MS = 450;
const FADE_OUT_MS = 500;

interface IntroScreenProps {
    onComplete: () => void;
}

const IntroScreen = ({ onComplete }: IntroScreenProps) => {
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isVisible, setIsVisible] = useState(true);
    const [isFadingOut, setIsFadingOut] = useState(false);

    useEffect(() => {
        const timer = setInterval(() => {
            setIsVisible(false);

            setTimeout(() => {
                setCurrentIndex((prev) => {
                    const next = prev + 1;
                    if (next >= languages.length) {
                        clearInterval(timer);
                        setIsFadingOut(true);
                        setTimeout(() => onComplete(), FADE_OUT_MS);
                        return prev;
                    }
                    return next;
                });
                setIsVisible(true);
            }, 200);
        }, INTERVAL_MS);

        return () => clearInterval(timer);
    }, [onComplete]);

    const current = languages[currentIndex];

    return (
        <div
            className="intro-screen"
            style={{ opacity: isFadingOut ? 0 : 1 }}
        >
            <SparkleBackground />

            <div className="intro-content">
                {/* Project name */}
                <h1 className="intro-title">
                    Voice OS <span className="intro-title-accent">Bharat</span>
                </h1>

                {/* Language rotation */}
                <div className="intro-language-container">
                    <div
                        className="intro-language"
                        style={{
                            opacity: isVisible ? 1 : 0,
                            transform: isVisible ? 'translateY(0)' : 'translateY(-16px)',
                        }}
                    >
                        <span className="intro-language-native">{current.native}</span>
                        <span className="intro-language-english">{current.english}</span>
                    </div>
                </div>

                {/* Subtitle */}
                <p className="intro-subtitle">
                    Multilingual Voice Assistant for Bharat
                </p>
            </div>
        </div>
    );
};

export default IntroScreen;
