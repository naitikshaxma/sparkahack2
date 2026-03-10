import { useState, useEffect, useRef, useCallback } from 'react';
import { Play, Pause, Volume2 } from 'lucide-react';
import { findVoice } from '@/lib/voiceUtils';

interface VoicePlayerProps {
    text: string;
    langCode: string;
    autoPlay: boolean;
    onPlayStart?: () => void;
    onPlayEnd?: () => void;
}


const VoicePlayer = ({ text, langCode, autoPlay, onPlayStart, onPlayEnd }: VoicePlayerProps) => {
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);
    const [elapsed, setElapsed] = useState(0);
    const [duration, setDuration] = useState(0);
    const startTimeRef = useRef(0);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const hasAutoPlayed = useRef(false);

    const estimatedDuration = Math.max(2, text.length * 0.08); // rough estimate in seconds

    const stopTracking = useCallback(() => {
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
        }
    }, []);

    const startTracking = useCallback(() => {
        stopTracking();
        startTimeRef.current = Date.now();
        setDuration(estimatedDuration);
        intervalRef.current = setInterval(() => {
            const elapsed = (Date.now() - startTimeRef.current) / 1000;
            setElapsed(elapsed);
            setProgress(Math.min((elapsed / estimatedDuration) * 100, 100));
        }, 100);
    }, [estimatedDuration, stopTracking]);

    const speak = useCallback(() => {
        if (!('speechSynthesis' in window)) return;
        speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        const voices = speechSynthesis.getVoices();
        const voice = findVoice(voices, langCode);

        if (voice) {
            utterance.voice = voice;
            utterance.lang = voice.lang;
        } else {
            utterance.lang = langCode === 'en' ? 'en-IN' : `${langCode}-IN`;
        }

        utterance.rate = 0.9;
        utterance.pitch = 1;
        utterance.volume = 1;

        utterance.onstart = () => {
            setIsPlaying(true);
            startTracking();
            onPlayStart?.();
        };

        utterance.onend = () => {
            setIsPlaying(false);
            setProgress(100);
            stopTracking();
            onPlayEnd?.();
        };

        utterance.onerror = () => {
            setIsPlaying(false);
            stopTracking();
            onPlayEnd?.();
        };

        speechSynthesis.speak(utterance);
        setTimeout(() => { if (speechSynthesis.paused) speechSynthesis.resume(); }, 150);
    }, [text, langCode, startTracking, stopTracking, onPlayStart, onPlayEnd]);

    const togglePlay = useCallback(() => {
        if (isPlaying) {
            speechSynthesis.cancel();
            setIsPlaying(false);
            stopTracking();
        } else {
            speak();
        }
    }, [isPlaying, speak, stopTracking]);

    /* Auto-play on mount */
    useEffect(() => {
        if (!autoPlay || hasAutoPlayed.current) return;
        hasAutoPlayed.current = true;

        const voices = speechSynthesis.getVoices();
        if (voices.length > 0) {
            setTimeout(speak, 500);
        } else {
            const handler = () => {
                const v = speechSynthesis.getVoices();
                if (v.length > 0) {
                    speechSynthesis.removeEventListener('voiceschanged', handler);
                    setTimeout(speak, 500);
                }
            };
            speechSynthesis.addEventListener('voiceschanged', handler);
            setTimeout(() => { if (!hasAutoPlayed.current) speak(); }, 1500);
        }

        return () => { speechSynthesis.cancel(); stopTracking(); };
    }, [autoPlay, speak, stopTracking]);

    const formatTime = (s: number) => {
        const mins = Math.floor(s / 60);
        const secs = Math.floor(s % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div className="bg-[#111111] border border-[#2a2a2a] rounded-xl p-5 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-body font-medium text-[#9ca3af] uppercase tracking-wider">
                    Voice Response
                </h3>
                {/* Speaker animation */}
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

            {/* Custom player controls */}
            <div className="flex items-center gap-3">
                {/* Play/Pause button */}
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

                {/* Progress bar */}
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

                    {/* Time indicator */}
                    <span className="text-xs text-[#9ca3af] font-body tabular-nums w-14 text-right shrink-0">
                        {formatTime(elapsed)} / {formatTime(duration || estimatedDuration)}
                    </span>
                </div>

                {/* Volume icon */}
                <Volume2 className={`w-4 h-4 shrink-0 transition-colors duration-300 ${isPlaying ? 'text-[#f59e0b]' : 'text-[#9ca3af]'
                    }`} />
            </div>

            {/* Response text preview */}
            <p className="text-xs text-[#9ca3af]/60 font-body leading-relaxed line-clamp-2">
                {text}
            </p>
        </div>
    );
};

export default VoicePlayer;
