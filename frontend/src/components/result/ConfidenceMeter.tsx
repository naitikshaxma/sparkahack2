import { useEffect, useState } from 'react';

interface ConfidenceMeterProps {
    confidence: number; // 0-100
    visible: boolean;
}

const ConfidenceMeter = ({ confidence, visible }: ConfidenceMeterProps) => {
    const [animatedValue, setAnimatedValue] = useState(0);

    useEffect(() => {
        if (!visible) { setAnimatedValue(0); return; }
        const timer = setTimeout(() => setAnimatedValue(confidence), 100);
        return () => clearTimeout(timer);
    }, [visible, confidence]);

    const getColor = (val: number) => {
        if (val >= 80) return '#14b8a6';
        if (val >= 50) return '#f59e0b';
        return '#dc2626';
    };

    const color = getColor(animatedValue);
    const radius = 42; // reduced from 52
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (animatedValue / 100) * circumference;

    return (
        <div
            className="transition-all duration-700 ease-out"
            style={{
                opacity: visible ? 1 : 0,
                transform: visible ? 'translateY(0)' : 'translateY(8px)',
            }}
        >
            <div className="flex items-center gap-4">
                {/* Circular meter — reduced size */}
                <div className="relative w-24 h-24">
                    <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                        <circle
                            cx="50" cy="50" r={radius}
                            fill="none"
                            stroke="#2a2a2a"
                            strokeWidth="6"
                        />
                        <circle
                            cx="50" cy="50" r={radius}
                            fill="none"
                            stroke={color}
                            strokeWidth="6"
                            strokeLinecap="round"
                            strokeDasharray={circumference}
                            strokeDashoffset={strokeDashoffset}
                            className="transition-all duration-1000 ease-out"
                        />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span
                            className="text-lg font-heading font-bold tabular-nums transition-colors duration-500"
                            style={{ color }}
                        >
                            {animatedValue}%
                        </span>
                    </div>
                </div>

                <div>
                    <span className="text-xs font-body text-[#9ca3af] uppercase tracking-wider block">
                        Confidence
                    </span>
                    <span className="text-xs font-body text-[#555555] mt-0.5 block">
                        Model certainty
                    </span>
                </div>
            </div>
        </div>
    );
};

export default ConfidenceMeter;
