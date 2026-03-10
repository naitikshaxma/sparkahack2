import { Mic, Play, Pause } from 'lucide-react';
import { useState } from 'react';

interface AudioPreviewCardProps {
    language: string;
    languageCode: string;
    duration: string;
    isProcessing: boolean;
}

const langColors: Record<string, string> = {
    hi: '#f59e0b', en: '#9ca3af', mr: '#ea580c', bn: '#dc2626', ta: '#14b8a6',
    te: '#b91c1c', kn: '#16a34a', ml: '#7c3aed', pa: '#d97706', gu: '#2563eb',
};

const AudioPreviewCard = ({ language, languageCode, duration, isProcessing }: AudioPreviewCardProps) => {
    const [isPlaying, setIsPlaying] = useState(false);
    const accent = langColors[languageCode] || '#f59e0b';

    return (
        <div className="bg-[#111111] border border-[#2a2a2a] rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-body font-medium text-[#9ca3af] uppercase tracking-wider">
                Audio Input
            </h3>

            {/* Audio waveform preview */}
            <div className="flex items-center gap-3">
                <button
                    onClick={() => setIsPlaying(!isPlaying)}
                    className="w-10 h-10 rounded-full bg-[#1a1a1a] border border-[#2a2a2a] flex items-center justify-center transition-colors hover:border-[#f59e0b]/40"
                >
                    {isPlaying ? (
                        <Pause className="w-4 h-4 text-[#f5f5f5]" />
                    ) : (
                        <Play className="w-4 h-4 text-[#f5f5f5] ml-0.5" />
                    )}
                </button>

                {/* Mini waveform bars */}
                <div className="flex items-center gap-[2px] flex-1 h-8">
                    {Array.from({ length: 40 }).map((_, i) => {
                        const height = 20 + Math.sin(i * 0.8) * 40 + Math.random() * 20;
                        return (
                            <div
                                key={i}
                                className="flex-1 rounded-full transition-all duration-300"
                                style={{
                                    height: `${height}%`,
                                    backgroundColor: isProcessing
                                        ? `${accent}40`
                                        : `${accent}80`,
                                    opacity: isProcessing ? 0.4 + Math.sin(i * 0.3) * 0.3 : 1,
                                }}
                            />
                        );
                    })}
                </div>

                <span className="text-xs text-[#9ca3af] font-body tabular-nums">
                    {duration}
                </span>
            </div>

            {/* Language badge */}
            <div className="flex items-center gap-2">
                <Mic className="w-3.5 h-3.5 text-[#9ca3af]" />
                <span
                    className="text-xs font-body font-medium px-2.5 py-1 rounded-full border"
                    style={{
                        color: accent,
                        borderColor: `${accent}30`,
                        backgroundColor: `${accent}10`,
                    }}
                >
                    {language} detected
                </span>
            </div>
        </div>
    );
};

export default AudioPreviewCard;
