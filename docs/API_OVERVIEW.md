# API Overview

## Core Endpoints

- GET /health: service readiness and component status
- GET /metrics: observability counters
- POST /api/intent: intent detection
- POST /api/transcribe: speech-to-text
- POST /api/tts: text-to-speech
- POST /api/tts-stream: streaming audio bytes
- POST /api/tts-interrupt: interrupt current TTS playback
- GET /api/voice-state: state machine snapshot by session
- GET /api/voice-analytics: interruption and latency analytics
- POST /api/process-text: standard text processing response
- POST /api/process-text-stream: NDJSON streaming response path
- POST /api/process-audio: audio or transcript processing path
- POST /api/ocr: OCR extraction and profile merge
- POST /api/autofill: browser automation trigger
- POST /api/reset-session: clear and recreate session

## Streaming Contract

process-text-stream returns NDJSON lines with event envelopes:
- meta: response payload and conversation metadata
- audio_chunk: sequence, text segment, and base64 chunk
- interrupted: interrupt marker for active stream
- done: stream completion marker

## Headers

- x-language: input language hint (en or hi)
- x-request-id: request correlation id returned by middleware
- x-api-key or Bearer token: optional auth when enabled
