import axios from 'axios';
import { getUserId, type VoiceResponse } from '@/types';

const api = axios.create({
    baseURL: (import.meta.env.VITE_BACKEND_URL || '') + '/api',
    timeout: 90000, // 90s — allow for ML processing
});

/**
 * POST /api/voice/process
 * Sends audio blob + stable user_id to the backend.
 * Returns spec-compliant VoiceResponse.
 */
export const processVoice = async (audioBlob: Blob): Promise<VoiceResponse> => {
    const userId = getUserId();
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('user_id', userId);

    const response = await api.post<VoiceResponse>('/voice/process', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
};

export default api;
