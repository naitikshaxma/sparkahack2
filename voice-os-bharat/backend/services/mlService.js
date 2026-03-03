const axios = require('axios');
const fs = require('fs');
const FormData = require('form-data');

const ML_SERVICE_URL = process.env.ML_SERVICE_URL || 'http://localhost:8000';

/**
 * Forward audio file to the FastAPI ML service for processing.
 * @param {string} audioPath - Path to the uploaded audio file
 * @param {string} userId - Stable user ID from frontend
 * @returns {Promise<object>} ML service response
 */
const forwardToML = async (audioPath, userId) => {
    try {
        const form = new FormData();
        form.append('audio', fs.createReadStream(audioPath));
        form.append('user_id', userId);

        const response = await axios.post(`${ML_SERVICE_URL}/process`, form, {
            headers: {
                ...form.getHeaders(),
            },
            timeout: 60000, // 60s timeout for ML processing
        });

        return response.data;
    } catch (error) {
        if (error.response) {
            throw new Error(`ML Service error: ${error.response.status} — ${JSON.stringify(error.response.data)}`);
        }
        throw new Error(`ML Service unreachable: ${error.message}`);
    }
};

/**
 * Fetch audio file from ML service via internal URL.
 * @param {string} filename - Filename returned by ML service
 * @returns {Promise<Buffer>} Audio file buffer
 */
const fetchAudioFromML = async (filename) => {
    try {
        const response = await axios.get(`${ML_SERVICE_URL}/static/audio/${filename}`, {
            responseType: 'arraybuffer',
        });
        return Buffer.from(response.data);
    } catch (error) {
        throw new Error(`Failed to fetch audio from ML service: ${error.message}`);
    }
};

module.exports = { forwardToML, fetchAudioFromML };
