import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import WaveformVisualizer from '@/components/WaveformVisualizer';
import IntentBadge from '@/components/IntentBadge';
import ResponseCard from '@/components/ResponseCard';
import { Mic, RotateCcw, LayoutDashboard } from 'lucide-react';
import type { VoiceResponse } from '@/types';

const langColors: Record<string, string> = {
    hi: '#f59e0b', en: '#9ca3af', mr: '#ea580c', bn: '#dc2626', ta: '#14b8a6',
    te: '#b91c1c', kn: '#16a34a', ml: '#7c3aed', pa: '#d97706', gu: '#2563eb',
};

/**
 * Result page — displays real API response from the backend.
 * State is passed via react-router navigate() from AudioRecorder.
 */
const Result = () => {
    const navigate = useNavigate();
    const location = useLocation();

    const state = location.state as {
        language?: string;
        languageCode?: string;
        response?: VoiceResponse;
    } | null;

    const langCode = state?.languageCode || 'en';
    const langName = state?.language || 'English';
    const response = state?.response;
    const accent = langColors[langCode] || '#f59e0b';

    const [showResults, setShowResults] = useState(false);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    // Graceful redirect if navigated here directly without data
    useEffect(() => {
        if (!response) {
            navigate('/', { replace: true });
        }
    }, [response, navigate]);

    useEffect(() => {
        const timer = setTimeout(() => setShowResults(true), 400);
        return () => clearTimeout(timer);
    }, []);

    // Auto-play TTS audio when results appear
    useEffect(() => {
        if (showResults && response?.audio_url && audioRef.current) {
            audioRef.current.play().catch(() => {/* autoplay blocked */ });
        }
    }, [showResults, response?.audio_url]);

    const handleAskAgain = useCallback(() => navigate('/'), [navigate]);

    if (!response) return null;

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
                        <span className="text-[#9ca3af] text-sm font-body hidden sm:block">Voice Assistant</span>
                    </div>
                </nav>

                {/* Page header */}
                <div className="max-w-7xl mx-auto w-full px-4 sm:px-6 pt-6 pb-1">
                    <h1 className="text-2xl md:text-3xl font-heading font-bold text-[#f5f5f5]">
                        Voice Assistant
                    </h1>
                    <p className="mt-1 text-sm font-body text-[#9ca3af]">Here are your results</p>

                    {/* Recognized speech */}
                    {response.recognized_text && (
                        <div className="mt-2 px-3 py-1.5 rounded-md bg-[#111111] border border-[#2a2a2a] inline-block">
                            <span className="text-[11px] text-[#555555] font-body">You said: </span>
                            <span className="text-xs text-[#9ca3af] font-body">"{response.recognized_text}"</span>
                        </div>
                    )}
                </div>

                {/* Three-column grid */}
                <div className="max-w-7xl mx-auto w-full px-4 sm:px-6 py-4 flex-1">
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

                        {/* LEFT — Audio metadata + Intent */}
                        <div className="space-y-4">
                            {/* Language + Intent */}
                            <div className="bg-[#111111] border border-[#2a2a2a] rounded-xl p-5 space-y-4">
                                <div className="flex items-center gap-2">
                                    <Mic className="w-3.5 h-3.5 text-[#9ca3af]" />
                                    <span
                                        className="text-xs font-body font-medium px-2.5 py-1 rounded-full border"
                                        style={{ color: accent, borderColor: `${accent}30`, backgroundColor: `${accent}10` }}
                                    >
                                        {langName} detected
                                    </span>
                                </div>
                                {/* Confidence score */}
                                <div className="space-y-1">
                                    <div className="flex justify-between text-xs font-body text-[#9ca3af]">
                                        <span>Prediction Score</span>
                                        <span style={{ color: accent }}>{response.confidence.toFixed(1)}%</span>
                                    </div>
                                    <div className="h-1.5 bg-[#222] rounded-full overflow-hidden">
                                        <div
                                            className="h-full rounded-full transition-all duration-700"
                                            style={{ width: `${Math.min(response.confidence, 100)}%`, backgroundColor: accent }}
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Intent badge */}
                            <div className="bg-[#111111] border border-[#2a2a2a] rounded-xl p-5 space-y-4">
                                <IntentBadge
                                    intent={response.intent}
                                    category="general"
                                    confidence={response.confidence}
                                    visible={showResults}
                                />
                            </div>

                            {/* TTS audio player — shown only if audio_url is available */}
                            {response.audio_url && (
                                <div className="bg-[#111111] border border-[#2a2a2a] rounded-xl p-5">
                                    <h3 className="text-sm font-body font-medium text-[#9ca3af] uppercase tracking-wider mb-3">
                                        Voice Response
                                    </h3>
                                    <audio
                                        ref={audioRef}
                                        controls
                                        src={response.audio_url}
                                        className="w-full"
                                        style={{ filter: 'invert(1) hue-rotate(180deg)' }}
                                    />
                                </div>
                            )}
                        </div>

                        {/* CENTER — Waveform processing animation */}
                        <div className="space-y-4">
                            <WaveformVisualizer isProcessing={false} />
                        </div>

                        {/* RIGHT — Structured response card */}
                        <div className="space-y-4">
                            <ResponseCard
                                confirmation=""
                                explanation={response.response_text}
                                nextStep=""
                                visible={showResults}
                                responseText={response.response_text}
                                langCode={langCode}
                                autoPlay={false}
                            />
                        </div>
                    </div>

                    {/* Action buttons */}
                    <div className="mt-6 flex justify-center">
                        <div
                            className="flex flex-col sm:flex-row gap-2.5 transition-all duration-700 ease-out"
                            style={{ opacity: showResults ? 1 : 0, transform: showResults ? 'translateY(0)' : 'translateY(8px)' }}
                        >
                            <button
                                onClick={handleAskAgain}
                                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#f59e0b] text-black font-body font-medium text-sm transition-all duration-200 hover:bg-[#d97706] active:scale-[0.98]"
                            >
                                <RotateCcw className="w-3.5 h-3.5" />
                                Ask Again
                            </button>
                            <button
                                onClick={() => navigate('/')}
                                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#1a1a1a] border border-[#2a2a2a] text-[#9ca3af] font-body font-medium text-sm transition-all duration-200 hover:bg-[#222222] hover:border-[#3a3a3a] hover:text-[#f5f5f5] active:scale-[0.98]"
                            >
                                <LayoutDashboard className="w-3.5 h-3.5" />
                                Dashboard
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Result;
