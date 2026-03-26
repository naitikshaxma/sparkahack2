# Voice OS Bharat

## Project Overview
Voice OS Bharat is a multilingual AI voice assistant for government-scheme guidance.  
It accepts voice or text input, transcribes speech, detects intent, retrieves relevant scheme information, and returns structured responses with synthesized audio.

## Architecture
- `frontend/`: React + Vite client for voice capture, language selection, and response display.
- `backend/`: FastAPI application that orchestrates STT, intent inference, scheme retrieval, and TTS.
- `datasets/`: canonical datasets used by backend services (`schemes_dataset.json`).
- `models/`: local model artifacts (kept out of git by default).
- `scripts/`: utility scripts (for example, dataset generation).
- `tests/`: local pipeline/integration tests.
- `docs/`: project documentation assets.

Request flow:
1. Frontend sends text/audio to FastAPI endpoints.
2. Backend transcribes audio with Whisper (when needed).
3. Backend runs retrieval + intent routing.
4. Backend generates response text and TTS audio.
5. Frontend renders the response and plays audio.

## Tech Stack
- Backend: FastAPI, Uvicorn, PyTorch, Transformers, OpenAI Whisper, RapidFuzz, gTTS
- Frontend: React, TypeScript, Vite, Tailwind CSS
- Data/ML: JSON scheme dataset + local HuggingFace-style intent model artifacts

## Setup Instructions

### 1. Backend
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8099
```

### 2. Frontend
```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

### 3. Environment
```powershell
Copy-Item .env.example .env
```
Update `.env` if you need custom runtime values.
Optional overrides:
- `CORS_ALLOW_ORIGINS` to control allowed frontend origins
- `SESSION_STORE_BACKEND` to force `auto|redis|memory`
- `TTS_RETRY_ATTEMPTS` to retry transient TTS failures
- `TTS_RETRY_BACKOFF_MS` for TTS retry backoff in milliseconds
- `STREAM_CHUNK_DELAY_MS` to throttle streaming chunk emission (ms)
- `VITE_DEV_BACKEND_URL` to control the Vite proxy target
- `VITE_DEV_PORT` to control the Vite dev server port
- `MAX_CONCURRENT_REQUESTS` to cap concurrent API requests
- `CONCURRENCY_ACQUIRE_TIMEOUT_SECONDS` to limit semaphore wait time
- `REQUEST_TIMEOUT_SECONDS` for non-streaming endpoint timeouts
- `STREAM_MAX_DURATION_SECONDS` for streaming endpoint max duration
- `MAX_VOICE_STATE_ENTRIES` to cap voice state cache size
- `MAX_ASYNC_LOCKS` to cap async session lock cache

Security notes:
- Backend startup validates critical env values and fails fast if required secrets are missing or placeholders.
- Never commit real credentials in `.env`; keep only placeholders in `.env.example`.
- Install repository hooks to block secret commits:

```powershell
./scripts/install_git_hooks.ps1
```

If a secret is exposed, follow [docs/SECRET_HISTORY_CLEANUP.md](docs/SECRET_HISTORY_CLEANUP.md).

## API Endpoints

- `GET /health`
  - Service health + model and dataset readiness.

- `POST /api/transcribe`
  - Multipart form: `audio`, optional `language`
  - Returns transcript text.

- `POST /api/intent`
  - JSON: `{ "text": "..." }`
  - Returns detected intent and confidence.

- `POST /api/tts`
  - JSON: `{ "text": "...", "language": "en|hi" }`
  - Returns base64 audio payload.

- `POST /api/process-text`
  - Multipart form: `text`, `user_id`, optional `language`
  - Returns full assistant response (intent + text + audio).

- `POST /api/process-audio`
  - Multipart form: `audio` or `text`, `user_id`, optional `language`
  - Returns full assistant response (transcript + intent + text + audio).

## Frontend Launch Features

- Real-time streamed response rendering with audio/text sync
- Voice lifecycle UX: listening, processing, speaking, interrupted
- Barge-in support and instant interruption handling
- Failsafe text input when microphone flow is unavailable
- Development-only debug panel for voice state, latency, detected language, and request id
- Conversation history timeline persisted per active session id
- Demo mode toggle with guided preloaded prompts

## Deployment Configuration

- Frontend runtime endpoints are configured through environment variables:
  - `VITE_API_BASE_URL`
  - `VITE_BACKEND_URL` (backward-compatible alias)
  - `VITE_DEV_BACKEND_URL` (dev proxy target for Vite)
  - `VITE_DEV_PORT` (dev server port override)
- Production template: [frontend/.env.production](frontend/.env.production)

## Documentation Index

- API reference: [docs/API_OVERVIEW.md](docs/API_OVERVIEW.md)
- Architecture summary: [docs/ARCHITECTURE_SUMMARY.md](docs/ARCHITECTURE_SUMMARY.md)
- Secret recovery runbook: [docs/SECRET_HISTORY_CLEANUP.md](docs/SECRET_HISTORY_CLEANUP.md)
- Release checklist: [docs/RELEASE_CHECKLIST_v1.0.md](docs/RELEASE_CHECKLIST_v1.0.md)

## Release Preparation (v1.0)

Suggested release commands:

```powershell
git tag v1.0
git push origin v1.0
```
