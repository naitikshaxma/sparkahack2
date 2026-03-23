# Architecture Summary

## Frontend

- React + Vite single-page app
- Centralized voice UX state in Zustand store
- Streaming text and audio orchestration in voice interaction layer
- Development-only debug panel for voice state, language, latency, and request id
- Conversation history persisted by session key for consistent demo flow

## Backend

- FastAPI app factory with middleware policies
- Modular route layer: intent, voice, system
- Service container for intent, conversation, STT, TTS, OCR, system service boundaries
- Session persistence abstraction with Redis-first fallback
- Analytics modules for intent metrics and voice interaction metrics

## Voice Pipeline

1. Capture speech or text input
2. Optional transcription path
3. Intent + conversation response generation
4. Stream metadata and audio chunks back to client
5. Barge-in interruption respected by voice state
6. Frontend syncs streamed text and audio playback

## Reliability and Safety

- Input validation and suspicious payload detection
- Request size and rate limiting
- Optional API key enforcement
- Structured logging and request id correlation
