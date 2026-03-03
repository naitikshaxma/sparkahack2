import { useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic, Loader2, Square } from 'lucide-react';
import { processVoice } from '@/services/api';
import type { VoiceResponse } from '@/types';

interface Language {
    code: string;
    name: string;
    nativeName: string;
    greeting: string;
}

interface AudioRecorderProps {
    language: Language;
    onBack: () => void;
}

const prompts: Record<string, { idle: string; recording: string; processing: string }> = {
    hi: { idle: 'बोलने के लिए टैप करें', recording: 'सुन रहा हूं...', processing: 'प्रक्रिया हो रही है...' },
    en: { idle: 'Tap to speak', recording: 'Listening...', processing: 'Processing...' },
    mr: { idle: 'बोलण्यासाठी टॅप करा', recording: 'ऐकत आहे...', processing: 'प्रक्रिया होत आहे...' },
    bn: { idle: 'বলতে ট্যাপ করুন', recording: 'শুনছি...', processing: 'প্রক্রিয়া হচ্ছে...' },
    ta: { idle: 'பேச தட்டவும்', recording: 'கேட்கிறேன்...', processing: 'செயலாக்கம்...' },
    te: { idle: 'మాట్లాడటానికి నొక్కండి', recording: 'వింటున్నాను...', processing: 'ప్రాసెసింగ్...' },
    kn: { idle: 'ಮಾತನಾಡಲು ಟ್ಯಾಪ್ ಮಾಡಿ', recording: 'ಕೇಳುತ್ತಿದ್ದೇನೆ...', processing: 'ಸಂಸ್ಕರಣೆ...' },
    ml: { idle: 'സംസാരിക്കാൻ ടാപ്പ് ചെയ്യുക', recording: 'കേൾക്കുന്നു...', processing: 'പ്രോസസ്സ് ചെയ്യുന്നു...' },
    pa: { idle: 'ਬੋਲਣ ਲਈ ਟੈਪ ਕਰੋ', recording: 'ਸੁਣ ਰਿਹਾ ਹਾਂ...', processing: 'ਪ੍ਰਕਿਰਿਆ ਹੋ ਰਹੀ ਹੈ...' },
    gu: { idle: 'બોલવા ટૅપ કરો', recording: 'સાંભળી રહ્યો છું...', processing: 'પ્રક્રિયા...' },
};

const backLabels: Record<string, string> = {
    hi: 'भाषा बदलें', en: 'Change language', mr: 'भाषा बदला',
    bn: 'ভাষা পরিবর্তন করুন', ta: 'மொழியை மாற்றவும்', te: 'భాష మార్చండి',
    kn: 'ಭಾಷೆ ಬದಲಾಯಿಸಿ', ml: 'ഭാഷ മാറ്റുക', pa: 'ਭਾਸ਼ਾ ਬਦਲੋ', gu: 'ભાષા બદલો',
};

const langAccents: Record<string, string> = {
    hi: '#f59e0b', en: '#9ca3af', mr: '#ea580c', bn: '#dc2626', ta: '#14b8a6',
    te: '#b91c1c', kn: '#16a34a', ml: '#7c3aed', pa: '#d97706', gu: '#2563eb',
};

type RecordState = 'idle' | 'recording' | 'processing' | 'error';

const AudioRecorder = ({ language, onBack }: AudioRecorderProps) => {
    const navigate = useNavigate();
    const [recordState, setRecordState] = useState<RecordState>('idle');
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);
    const streamRef = useRef<MediaStream | null>(null);

    const prompt = prompts[language.code] || prompts.en;
    const backLabel = backLabels[language.code] || backLabels.en;
    const accent = langAccents[language.code] || '#f59e0b';

    const handleBack = useCallback(() => {
        // Stop any active recording stream
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((t) => t.stop());
        }
        onBack();
    }, [onBack]);

    const startRecording = useCallback(async () => {
        setErrorMsg(null);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;
            chunksRef.current = [];

            const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            mediaRecorderRef.current = mr;

            mr.ondataavailable = (e) => {
                if (e.data.size > 0) chunksRef.current.push(e.data);
            };

            mr.onstop = async () => {
                stream.getTracks().forEach((t) => t.stop());
                streamRef.current = null;

                const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
                if (audioBlob.size === 0) {
                    setErrorMsg('No audio captured. Please try again.');
                    setRecordState('idle');
                    return;
                }

                setRecordState('processing');
                try {
                    const result: VoiceResponse = await processVoice(audioBlob);
                    navigate('/result', {
                        state: {
                            language: language.name,
                            languageCode: language.code,
                            response: result,
                        },
                    });
                } catch (apiErr: any) {
                    setErrorMsg(apiErr?.response?.data?.error || 'Server error. Please try again.');
                    setRecordState('error');
                }
            };

            mr.start();
            setRecordState('recording');
        } catch (err: any) {
            if (err.name === 'NotAllowedError') {
                setErrorMsg('Microphone access denied. Please allow microphone access and try again.');
            } else {
                setErrorMsg('Could not access microphone. Please check your device settings.');
            }
            setRecordState('error');
        }
    }, [language, navigate]);

    const stopRecording = useCallback(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop();
        }
    }, []);

    const handleMicClick = useCallback(() => {
        if (recordState === 'recording') {
            stopRecording();
        } else if (recordState === 'idle' || recordState === 'error') {
            startRecording();
        }
    }, [recordState, startRecording, stopRecording]);

    const isRecording = recordState === 'recording';
    const isProcessing = recordState === 'processing';
    const isDisabled = isProcessing;

    return (
        <div className="min-h-screen bg-black flex flex-col relative">
            {/* Top bar */}
            <div className="relative z-10 flex items-center justify-between px-6 py-4">
                <button
                    onClick={handleBack}
                    className="flex items-center gap-2 text-sm font-body text-[#9ca3af] hover:text-[#f5f5f5] transition-colors"
                >
                    ← {backLabel}
                </button>
                <div
                    className="flex items-center gap-2 px-4 py-2 rounded-full border bg-[#111111] font-body text-sm font-medium"
                    style={{ borderColor: `${accent}40`, color: accent }}
                >
                    {language.nativeName}
                </div>
            </div>

            {/* Main content */}
            <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 -mt-8">
                {/* Mic Button */}
                <div className="relative flex items-center justify-center">
                    {isRecording && (
                        <>
                            <div className="absolute w-48 h-48 rounded-full bg-[#f59e0b]/10 animate-ping" style={{ animationDuration: '2s' }} />
                            <div className="absolute w-40 h-40 rounded-full bg-[#f59e0b]/15 animate-ping" style={{ animationDuration: '1.5s' }} />
                        </>
                    )}
                    <button
                        onClick={handleMicClick}
                        disabled={isDisabled}
                        className={`relative z-10 w-28 h-28 md:w-32 md:h-32 rounded-full flex items-center justify-center transition-all duration-300
                            ${isRecording ? 'bg-[#f59e0b] scale-105 shadow-[0_0_40px_rgba(245,158,11,0.3)]'
                                : 'bg-[#1a1a1a] border border-[#2a2a2a] shadow-[0_8px_32px_rgba(0,0,0,0.4)]'}
                            ${isDisabled ? 'opacity-70' : 'hover:scale-105 active:scale-95'}`}
                    >
                        {isProcessing ? (
                            <Loader2 className="w-10 h-10 text-[#f5f5f5] animate-spin" />
                        ) : isRecording ? (
                            <Square className="w-9 h-9 text-black fill-black" />
                        ) : (
                            <Mic className="w-10 h-10 text-[#f5f5f5]" />
                        )}
                    </button>
                </div>

                {/* Status text */}
                <div className="mt-10 text-center min-h-[80px]">
                    {errorMsg ? (
                        <p className="text-base text-red-400 font-body max-w-sm">{errorMsg}</p>
                    ) : (
                        <p className={`text-2xl md:text-3xl font-heading font-semibold transition-colors duration-300
                            ${isRecording ? 'text-[#f59e0b]' : isProcessing ? 'text-[#14b8a6]' : 'text-[#9ca3af]'}`}
                        >
                            {isProcessing ? prompt.processing : isRecording ? prompt.recording : prompt.idle}
                        </p>
                    )}
                </div>

                {/* Recording tip */}
                {isRecording && (
                    <p className="mt-4 text-[#555555] text-sm font-body">
                        {language.code === 'hi' ? 'रोकने के लिए टैप करें' : 'Tap again to stop recording'}
                    </p>
                )}
            </div>

            {/* Bottom hint */}
            <div className="relative z-10 py-6 text-center">
                <p className="text-[#555555] text-sm font-body">
                    {language.code === 'hi' ? 'माइक बटन दबाएं और बोलें' : 'Tap the microphone and speak clearly'}
                </p>
            </div>
        </div>
    );
};

export default AudioRecorder;
