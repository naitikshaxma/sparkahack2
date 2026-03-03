# Voice OS Bharat — AntiGravity

A multilingual AI voice assistant built for India, supporting 10 Indian languages.

## Project Structure

```
antigravity/
├── frontend/          # React + Vite + TypeScript + TailwindCSS
├── backend/           # Express.js (Node.js)
├── ml_service/        # FastAPI (Python)
└── README.md
```

## Quick Start

### Frontend (React)
```bash
cd frontend
npm install
npm run dev          # → http://localhost:8080
```

### Backend (Express)
```bash
cd backend
npm install
cp .env.example .env
npm run dev          # → http://localhost:5000
```

### ML Service (FastAPI)
```bash
cd ml_service
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

## Architecture

| Layer | Tech | Port | Purpose |
|-------|------|------|---------|
| Frontend | React + Vite | 8080 | UI, voice capture, result display |
| Backend | Express.js | 5000 | API gateway, session management, static files |
| ML Service | FastAPI | 8000 | Whisper STT, BERT intent, flow engine, TTS |

## Supported Languages

Hindi, English, Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam, Punjabi, Gujarati
