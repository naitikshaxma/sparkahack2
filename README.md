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
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
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
