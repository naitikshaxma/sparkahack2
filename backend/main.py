from __future__ import annotations

import base64
import io
import struct
import wave
from typing import Any, Dict

from fastapi import FastAPI, Request


app = FastAPI(title="Voice OS Backend", version="deploy-minimal")


def _silent_wav_base64(duration_ms: int = 320, sample_rate: int = 16000) -> str:
	frame_count = max(1, int(sample_rate * duration_ms / 1000))
	pcm = struct.pack("<h", 0) * frame_count
	buff = io.BytesIO()
	with wave.open(buff, "wb") as wav_file:
		wav_file.setnchannels(1)
		wav_file.setsampwidth(2)
		wav_file.setframerate(sample_rate)
		wav_file.writeframes(pcm)
	return base64.b64encode(buff.getvalue()).decode("utf-8")


def _ok(data: Dict[str, Any]) -> Dict[str, Any]:
	return {"success": True, "data": data}


@app.get("/")
def root() -> Dict[str, Any]:
	return _ok({"status": "ok", "service": "voice-os-backend"})


@app.get("/health")
def health() -> Dict[str, Any]:
	return _ok({"status": "ok"})


@app.get("/api/health")
def health_api() -> Dict[str, Any]:
	return health()


@app.get("/api/v1/health")
def health_api_v1() -> Dict[str, Any]:
	return health()


def _intent_payload(text: str, language: str) -> Dict[str, Any]:
	cleaned = (text or "").strip()
	if not cleaned:
		cleaned = "I need scheme information"
	message = (
		"I can help with scheme information, eligibility, and application steps. "
		"Please ask your next question."
	)
	return {
		"type": "general_query",
		"message": message,
		"confidence": 0.82,
		"language": language,
		"data": {
			"message": message,
			"scheme": None,
			"summary": f"Query received: {cleaned[:120]}",
			"next_step": "Ask about eligibility, documents, or how to apply.",
		},
	}


@app.post("/api/intent")
async def intent(request: Request) -> Dict[str, Any]:
	payload = await request.json()
	text = str((payload or {}).get("text") or "")
	language = str((payload or {}).get("language") or "en")
	response = _intent_payload(text, language)
	merged = {
		"success": True,
		"type": response["type"],
		"message": response["message"],
		"confidence": response["confidence"],
		"data": response["data"],
	}
	return merged


@app.post("/api/v1/intent")
async def intent_v1(request: Request) -> Dict[str, Any]:
	return await intent(request)


@app.post("/api/tts")
async def tts(request: Request) -> Dict[str, Any]:
	payload = await request.json()
	text = str((payload or {}).get("text") or "").strip()
	if not text:
		text = "Ready"
	audio_base64 = _silent_wav_base64()
	return {
		"success": True,
		"audio_base64": audio_base64,
		"data": {"audio_base64": audio_base64, "text": text},
	}


@app.post("/api/v1/tts")
async def tts_v1(request: Request) -> Dict[str, Any]:
	return await tts(request)


@app.post("/api/transcribe")
async def transcribe(request: Request) -> Dict[str, Any]:
	raw = await request.body()
	transcript = "Audio received" if raw else "No audio payload"
	return {
		"success": True,
		"transcript": transcript,
		"text": transcript,
		"data": {"transcript": transcript, "text": transcript},
	}


@app.post("/api/v1/transcribe")
async def transcribe_v1(request: Request) -> Dict[str, Any]:
	return await transcribe(request)
