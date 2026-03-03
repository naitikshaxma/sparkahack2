const fs = require('fs');
const path = require('path');
const { forwardToML } = require('../services/mlService');
const { getOrCreateSession, updateSession } = require('../services/sessionService');

/**
 * POST /api/voice/process
 * Receives audio file + user_id, forwards to ML service, returns spec-compliant JSON.
 */
const processVoice = async (req, res, next) => {
    try {
        if (!req.file) {
            return res.status(400).json({ error: 'No audio file uploaded' });
        }

        const userId = req.body.user_id;
        if (!userId) {
            return res.status(400).json({ error: 'user_id is required' });
        }

        const audioPath = req.file.path;

        // Get or create session keyed by user_id
        const session = getOrCreateSession(userId);
        updateSession(userId, { status: 'processing' });

        try {
            // Forward audio to ML service (FastAPI)
            const mlResponse = await forwardToML(audioPath, userId);

            // If ML service returned a TTS audio filename, fetch it via internal URL
            let audioUrl = null;
            if (mlResponse.audio_url) {
                const audioFileName = mlResponse.audio_url; // It's a filename now
                const staticAudioDir = path.join(__dirname, '..', 'static', 'audio');

                // Create directory if it doesn't exist
                if (!fs.existsSync(staticAudioDir)) {
                    fs.mkdirSync(staticAudioDir, { recursive: true });
                }

                const destPath = path.join(staticAudioDir, audioFileName);

                // Fetch file from ML service via HTTP
                const { fetchAudioFromML } = require('../services/mlService');
                const audioBuffer = await fetchAudioFromML(audioFileName);
                fs.writeFileSync(destPath, audioBuffer);

                audioUrl = `/static/audio/${audioFileName}`;
            }

            // Append turn to conversation history
            updateSession(userId, {
                status: 'complete',
                current_flow: mlResponse.intent || '',
                conversation_history: [
                    ...(session.conversation_history || []),
                    {
                        recognized_text: mlResponse.recognized_text,
                        intent: mlResponse.intent,
                        response_text: mlResponse.response_text,
                        timestamp: Date.now(),
                    },
                ],
            });

            // Cleanup uploaded file
            fs.unlink(audioPath, (err) => {
                if (err) console.error(`[Voice Controller] Failed to delete uploaded file: ${err.message}`);
            });

            // Return spec-compliant response
            res.json({
                recognized_text: mlResponse.recognized_text,
                intent: mlResponse.intent,
                confidence: mlResponse.confidence,
                response_text: mlResponse.response_text,
                audio_url: audioUrl,
            });
        } catch (mlError) {
            // Cleanup uploaded file on error
            fs.unlink(audioPath, (err) => {
                if (err) console.error(`[Voice Controller] Failed to delete uploaded file on error: ${err.message}`);
            });
            throw mlError;
        }
    } catch (error) {
        next(error);
    }
};

module.exports = { processVoice };
