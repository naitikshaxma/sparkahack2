interface IntentBadgeProps {
    intent: string;
    category: 'banking' | 'government' | 'complaint' | 'general';
    confidence: number;
    visible: boolean;
}

const categoryColors: Record<string, string> = {
    banking: '#f59e0b',
    government: '#d4a843',
    complaint: '#dc2626',
    general: '#14b8a6',
};

const IntentBadge = ({ intent, category, confidence, visible }: IntentBadgeProps) => {
    const accent = categoryColors[category] || '#9ca3af';

    return (
        <div
            className="transition-all duration-700 ease-out"
            style={{
                opacity: visible ? 1 : 0,
                transform: visible ? 'translateY(0)' : 'translateY(8px)',
            }}
        >
            <div
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-md border"
                style={{
                    backgroundColor: `${accent}08`,
                    borderColor: `${accent}30`,
                    boxShadow: `0 0 12px ${accent}08`,
                }}
            >
                <div
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: accent }}
                />
                <span
                    className="text-xs font-body font-semibold tracking-wide uppercase"
                    style={{ color: accent, letterSpacing: '0.05em' }}
                >
                    {intent}
                </span>
                <span className="text-[10px] text-[#555555] font-body tracking-wide">
                    · {category}
                </span>
                <span className="text-[10px] font-body font-medium" style={{ color: accent }}>
                    {confidence}%
                </span>
            </div>
        </div>
    );
};

export default IntentBadge;
