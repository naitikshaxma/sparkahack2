import { useEffect, useState } from 'react';

interface WaveformVisualizerProps {
    isProcessing: boolean;
}

const WaveformVisualizer = ({ isProcessing }: WaveformVisualizerProps) => {
    const [bars] = useState(() =>
        Array.from({ length: 24 }).map(() => ({
            delay: Math.random() * 0.8,
            baseHeight: 15 + Math.random() * 25,
        }))
    );

    const [dots, setDots] = useState('');

    useEffect(() => {
        if (!isProcessing) return;
        const interval = setInterval(() => {
            setDots((prev) => (prev.length >= 3 ? '' : prev + '.'));
        }, 500);
        return () => clearInterval(interval);
    }, [isProcessing]);

    return (
        <div className="bg-[#111111] border border-[#2a2a2a] rounded-xl p-6 flex flex-col items-center justify-center space-y-6">
            {/* Waveform bars */}
            <div className="flex items-end justify-center gap-1 h-20">
                {bars.map((bar, i) => (
                    <div
                        key={i}
                        className="w-1.5 rounded-full transition-all"
                        style={{
                            height: isProcessing ? `${bar.baseHeight + 40}%` : `${bar.baseHeight}%`,
                            backgroundColor: isProcessing ? '#f59e0b' : '#2a2a2a',
                            animation: isProcessing
                                ? `waveBar 0.8s ease-in-out ${bar.delay}s infinite alternate`
                                : 'none',
                            opacity: isProcessing ? 0.8 : 0.3,
                            transition: 'background-color 0.5s, opacity 0.5s',
                        }}
                    />
                ))}
            </div>

            {/* Status text */}
            <div className="text-center">
                <p className="text-sm font-body text-[#f59e0b] tracking-wide">
                    {isProcessing ? (
                        <>Analyzing speech{dots}</>
                    ) : (
                        <span className="text-[#14b8a6]">Analysis complete</span>
                    )}
                </p>
            </div>
        </div>
    );
};

export default WaveformVisualizer;
