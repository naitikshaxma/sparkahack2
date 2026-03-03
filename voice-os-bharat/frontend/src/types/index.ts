/** Voice processing response from the backend — matches spec exactly */
export interface VoiceResponse {
    recognized_text: string;
    intent: string;
    confidence: number;
    response_text: string;
    audio_url: string | null;
}

/** Session state for the frontend */
export interface SessionState {
    userId: string;
    status: 'idle' | 'recording' | 'processing' | 'complete';
    response?: VoiceResponse;
}

/**
 * Get or create a stable user_id for this browser tab.
 * Stored in sessionStorage so it persists across navigations but resets on new tab/window.
 */
export const getUserId = (): string => {
    const stored = sessionStorage.getItem('voice_os_user_id');
    if (stored) return stored;
    const id = crypto.randomUUID();
    sessionStorage.setItem('voice_os_user_id', id);
    return id;
};
