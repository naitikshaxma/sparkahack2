import { CheckCircle, Info, ArrowRight } from 'lucide-react';
import { useState, useEffect, useRef, useCallback } from 'react';
import { Play, Pause, Volume2 } from 'lucide-react';

interface ResponseCardProps {
    confirmation: string;
    explanation: string;
    nextStep: string;
    visible: boolean;
    // TTS props
    responseText: string;
    langCode: string;
    autoPlay?: boolean;
}

/* Voice matching helpers */
const langVoiceTags: Record<string, string[]> = {
    hi: ['hi-IN', 'hi'], en: ['en-IN', 'en-US', 'en-GB', 'en'],
    mr: ['mr-IN', 'mr'], bn: ['bn-IN', 'bn-BD', 'bn'],
    ta: ['ta-IN', 'ta'], te: ['te-IN', 'te'],
    kn: ['kn-IN', 'kn'], ml: ['ml-IN', 'ml'],
    pa: ['pa-IN', 'pa-Guru-IN', 'pa'], gu: ['gu-IN', 'gu'],
};

const langSearchNames: Record<string, string[]> = {
    hi: ['hindi', 'हिन्दी', 'swara'], en: ['english', 'heera'],
    mr: ['marathi'], bn: ['bengali', 'bangla'],
    ta: ['tamil'], te: ['telugu'],
    kn: ['kannada'], ml: ['malayalam'],
    pa: ['punjabi', 'panjabi'], gu: ['gujarati'],
};

function findVoice(voices: SpeechSynthesisVoice[], langCode: string): SpeechSynthesisVoice | null {
    const tags = langVoiceTags[langCode] || [`${langCode}-IN`, langCode];
    const localVoices = voices.filter((v) => v.localService);
    const remoteVoices = voices.filter((v) => !v.localService);
    for (const voiceSet of [localVoices, remoteVoices]) {
        for (const tag of tags) { const v = voiceSet.find((v) => v.lang === tag); if (v) return v; }
        for (const tag of tags) { const v = voiceSet.find((v) => v.lang.startsWith(tag)); if (v) return v; }
        const names = langSearchNames[langCode] || [];
        for (const name of names) { const v = voiceSet.find((v) => v.name.toLowerCase().includes(name.toLowerCase())); if (v) return v; }
    }
    return null;
}

const ResponseCard = ({ confirmation, explanation, nextStep, visible, responseText, langCode, autoPlay = false }: ResponseCardProps) => {
    /* TTS Player state */
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);
    const [elapsed, setElapsed] = useState(0);
    const [duration, setDuration] = useState(0);
    const startTimeRef = useRef(0);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const hasAutoPlayed = useRef(false);

    const estimatedDuration = Math.max(2, responseText.length * 0.08);

    const stopTracking = useCallback(() => {
        if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    }, []);

    const startTracking = useCallback(() => {
        stopTracking();
        startTimeRef.current = Date.now();
        setDuration(estimatedDuration);
        intervalRef.current = setInterval(() => {
            const el = (Date.now() - startTimeRef.current) / 1000;
            setElapsed(el);
            setProgress(Math.min((el / estimatedDuration) * 100, 100));
        }, 100);
    }, [estimatedDuration, stopTracking]);

    const speak = useCallback(() => {
        if (!('speechSynthesis' in window)) return;
        speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(responseText);
        const voices = speechSynthesis.getVoices();
        const voice = findVoice(voices, langCode);
        if (voice) { utterance.voice = voice; utterance.lang = voice.lang; }
        else { utterance.lang = langCode === 'en' ? 'en-IN' : `${langCode}-IN`; }
        utterance.rate = 0.9; utterance.pitch = 1; utterance.volume = 1;
        utterance.onstart = () => { setIsPlaying(true); startTracking(); };
        utterance.onend = () => { setIsPlaying(false); setProgress(100); stopTracking(); };
        utterance.onerror = () => { setIsPlaying(false); stopTracking(); };
        speechSynthesis.speak(utterance);
        setTimeout(() => { if (speechSynthesis.paused) speechSynthesis.resume(); }, 150);
    }, [responseText, langCode, startTracking, stopTracking]);

    const togglePlay = useCallback(() => {
        if (isPlaying) { speechSynthesis.cancel(); setIsPlaying(false); stopTracking(); }
        else { speak(); }
    }, [isPlaying, speak, stopTracking]);

    useEffect(() => {
        if (!autoPlay || hasAutoPlayed.current || !visible) return;
        hasAutoPlayed.current = true;
        const voices = speechSynthesis.getVoices();
        if (voices.length > 0) { setTimeout(speak, 500); }
        else {
            const handler = () => {
                const v = speechSynthesis.getVoices();
                if (v.length > 0) { speechSynthesis.removeEventListener('voiceschanged', handler); setTimeout(speak, 500); }
            };
            speechSynthesis.addEventListener('voiceschanged', handler);
        }
        return () => { speechSynthesis.cancel(); stopTracking(); };
    }, [autoPlay, visible, speak, stopTracking]);

    const formatTime = (s: number) => {
        const mins = Math.floor(s / 60);
        const secs = Math.floor(s % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div
            className="bg-[#111111] border border-[#2a2a2a] rounded-xl overflow-hidden transition-all duration-700 ease-out"
            style={{
                opacity: visible ? 1 : 0,
                transform: visible ? 'translateY(0)' : 'translateY(16px)',
            }}
        >
            <div className="px-5 py-4 border-b border-[#2a2a2a]">
                <h3 className="text-sm font-body font-medium text-[#9ca3af] uppercase tracking-wider">
                    Response
                </h3>
            </div>

            <div className="p-5 space-y-5">
                {/* Confirmation */}
                <div className="flex gap-3">
                    <CheckCircle className="w-5 h-5 text-[#14b8a6] mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs font-body text-[#9ca3af] uppercase tracking-wider mb-1">
                            Confirmation
                        </p>
                        <p className="text-sm font-body text-[#f5f5f5] leading-relaxed">
                            {confirmation}
                        </p>
                    </div>
                </div>

                {/* Divider */}
                <div className="border-t border-[#2a2a2a]" />

                {/* Explanation */}
                <div className="flex gap-3">
                    <Info className="w-5 h-5 text-[#f59e0b] mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs font-body text-[#9ca3af] uppercase tracking-wider mb-1">
                            Explanation
                        </p>
                        <p className="text-sm font-body text-[#f5f5f5] leading-relaxed">
                            {explanation}
                        </p>
                    </div>
                </div>

                {/* Divider */}
                <div className="border-t border-[#2a2a2a]" />

                {/* Next Step */}
                <div className="flex gap-3">
                    <ArrowRight className="w-5 h-5 text-[#d4a843] mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs font-body text-[#9ca3af] uppercase tracking-wider mb-1">
                            Next Step
                        </p>
                        <p className="text-sm font-body text-[#f5f5f5] leading-relaxed">
                            {nextStep}
                        </p>
                    </div>
                </div>

                {/* Divider */}
                <div className="border-t border-[#2a2a2a]" />

                {/* TTS Audio Player (integrated) */}
                <div className="space-y-3">
                    <div className="flex items-center justify-between">
                        <h4 className="text-sm font-body font-medium text-[#9ca3af] uppercase tracking-wider">
                            Voice Response
                        </h4>
                        {isPlaying && (
                            <div className="flex items-center gap-1">
                                <div className="voice-bar" style={{ animationDelay: '0s' }} />
                                <div className="voice-bar" style={{ animationDelay: '0.15s' }} />
                                <div className="voice-bar" style={{ animationDelay: '0.3s' }} />
                                <div className="voice-bar" style={{ animationDelay: '0.45s' }} />
                                <div className="voice-bar" style={{ animationDelay: '0.1s' }} />
                            </div>
                        )}
                    </div>

                    <div className="flex items-center gap-3">
                        <button
                            onClick={togglePlay}
                            className={`w-10 h-10 rounded-full flex items-center justify-center transition-all duration-200 shrink-0 ${isPlaying
                                ? 'bg-[#f59e0b] shadow-[0_0_20px_rgba(245,158,11,0.2)]'
                                : 'bg-[#1a1a1a] border border-[#2a2a2a] hover:border-[#f59e0b]/30'
                                }`}
                        >
                            {isPlaying ? (
                                <Pause className="w-4 h-4 text-black" />
                            ) : (
                                <Play className="w-4 h-4 text-[#f5f5f5] ml-0.5" />
                            )}
                        </button>

                        <div className="flex-1 flex items-center gap-3">
                            <div className="flex-1 h-1.5 bg-[#2a2a2a] rounded-full overflow-hidden">
                                <div
                                    className="h-full rounded-full transition-all duration-200 ease-linear"
                                    style={{
                                        width: `${progress}%`,
                                        backgroundColor: isPlaying ? '#f59e0b' : '#14b8a6',
                                    }}
                                />
                            </div>
                            <span className="text-xs text-[#9ca3af] font-body tabular-nums w-14 text-right shrink-0">
                                {formatTime(elapsed)} / {formatTime(duration || estimatedDuration)}
                            </span>
                        </div>

                        <Volume2 className={`w-4 h-4 shrink-0 transition-colors duration-300 ${isPlaying ? 'text-[#f59e0b]' : 'text-[#9ca3af]'
                            }`} />
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ResponseCard;
