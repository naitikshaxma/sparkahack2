require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const voiceRoutes = require('./routes/voiceRoutes');
const errorHandler = require('./middleware/errorHandler');

const app = express();
const PORT = process.env.PORT || 5000;

// Middleware
app.use(cors());
app.use(express.json());

// Serve TTS audio files statically
app.use('/static/audio', express.static(path.join(__dirname, 'static', 'audio')));

// Routes
app.use('/api/voice', voiceRoutes);

// Health check
app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', service: 'voice-os-backend' });
});

// Error handler (must be last)
app.use(errorHandler);

app.listen(PORT, () => {
    console.log(`[Voice OS Backend] Running on http://localhost:${PORT}`);
});

module.exports = app;
