import { useEffect, useRef } from 'react';

interface Particle {
    x: number;
    y: number;
    size: number;
    speed: number;
    opacity: number;
    twinkleSpeed: number;
    twinklePhase: number;
}

/** Displays active session / flow state info */
interface SessionPanelProps {
    sessionId: string;
    language: string;
    languageCode: string;
    status: 'recording' | 'processing' | 'complete' | 'idle';
    transcript?: string;
}

const statusLabels: Record<string, { label: string; color: string }> = {
    recording: { label: 'Recording', color: '#dc2626' },
    processing: { label: 'Processing', color: '#f59e0b' },
    complete: { label: 'Complete', color: '#14b8a6' },
    idle: { label: 'Idle', color: '#9ca3af' },
};

const SessionPanel = ({ sessionId, language, languageCode, status, transcript }: SessionPanelProps) => {
    const info = statusLabels[status] || statusLabels.idle;

    return (
        <div className="bg-[#111111] border border-[#2a2a2a] rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-body font-medium text-[#9ca3af] uppercase tracking-wider">
                    Session
                </h3>
                <div
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-body font-medium"
                    style={{
                        color: info.color,
                        borderColor: `${info.color}30`,
                        backgroundColor: `${info.color}08`,
                    }}
                >
                    <div
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ backgroundColor: info.color }}
                    />
                    {info.label}
                </div>
            </div>

            <div className="space-y-2 text-xs font-body">
                <div className="flex justify-between">
                    <span className="text-[#555555]">Session ID</span>
                    <span className="text-[#9ca3af] font-mono">{sessionId.slice(0, 12)}...</span>
                </div>
                <div className="flex justify-between">
                    <span className="text-[#555555]">Language</span>
                    <span className="text-[#9ca3af]">{language} ({languageCode})</span>
                </div>
                {transcript && (
                    <div className="pt-2 border-t border-[#2a2a2a]">
                        <span className="text-[#555555] block mb-1">Transcript</span>
                        <p className="text-[#9ca3af] leading-relaxed">"{transcript}"</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default SessionPanel;
