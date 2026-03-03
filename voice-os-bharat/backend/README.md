# Voice OS Backend

Express.js backend that acts as the intermediary between the React frontend and the FastAPI ML service.

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/voice/process` | Upload audio file + language for processing |
| GET | `/api/health` | Health check |

## Architecture

- **routes/voiceRoutes.js** — Multer config + route definitions
- **controllers/voiceController.js** — Request handling, session wiring
- **services/mlService.js** — Axios forwarding to FastAPI ML service
- **services/sessionService.js** — In-memory session store (Map + TTL)
- **middleware/errorHandler.js** — Central error handler
- **uploads/** — Temp audio files (deleted after forwarding)
- **static/audio/** — TTS .wav files served statically
