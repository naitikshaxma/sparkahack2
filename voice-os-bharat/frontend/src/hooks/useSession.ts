import { useState, useCallback } from 'react';
import { SessionState } from '@/types';

/**
 * Custom hook for managing session state throughout the voice interaction flow.
 */
const useSession = () => {
    const [session, setSession] = useState<SessionState>({
        sessionId: '',
        language: '',
        languageCode: '',
        status: 'idle',
    });

    const startSession = useCallback((language: string, languageCode: string) => {
        setSession({
            sessionId: crypto.randomUUID(),
            language,
            languageCode,
            status: 'recording',
        });
    }, []);

    const setRecording = useCallback(() => {
        setSession((prev) => ({ ...prev, status: 'recording' }));
    }, []);

    const setProcessing = useCallback((transcript?: string) => {
        setSession((prev) => ({ ...prev, status: 'processing', transcript }));
    }, []);

    const setComplete = useCallback((response?: any) => {
        setSession((prev) => ({ ...prev, status: 'complete', response }));
    }, []);

    const resetSession = useCallback(() => {
        setSession({
            sessionId: '',
            language: '',
            languageCode: '',
            status: 'idle',
        });
    }, []);

    return {
        session,
        startSession,
        setRecording,
        setProcessing,
        setComplete,
        resetSession,
    };
};

export default useSession;
