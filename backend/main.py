import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .bert_service import get_intent_model_status, predict_intent
from .flow_engine import generate_response
from .rag_service import get_rag_status
from .session_manager import get_session, update_session
from .tts_service import generate_tts
from .whisper_service import get_whisper_status, transcribe_audio, warmup_whisper

app = FastAPI(title="Voice OS Bharat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    warmup_whisper()


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "whisper": get_whisper_status(),
        "intent_model": get_intent_model_status(),
        "rag": get_rag_status(),
    }


def _debug_print(label: str, value: object) -> None:
    safe_value = str(value).encode("unicode_escape").decode("ascii")
    print(label, safe_value)


class IntentRequest(BaseModel):
    text: str


class TTSRequest(BaseModel):
    text: str
    language: str = "en"


def _process_transcript(transcript: str, user_id: str, language: str) -> dict:
    response_text, intent, confidence = generate_response(language=language, transcript=transcript)

    tts_input = " ".join(
        [response_text.get("confirmation", ""), response_text.get("explanation", ""), response_text.get("next_step", "")]
    ).strip()
    audio_base64 = generate_tts(tts_input, language)
    if not audio_base64:
        raise HTTPException(status_code=500, detail="TTS generation failed.")

    get_session(user_id)
    update_session(
        user_id,
        {
            "intent": intent,
            "transcript": transcript,
            "confidence": round(float(confidence) * 100.0, 2),
            "timestamp": time.time(),
        },
    )

    return {
        "transcript": transcript,
        "intent": intent,
        "confidence": round(float(confidence) * 100.0, 2),
        "response_text": response_text,
        "audio_base64": f"data:audio/mp3;base64,{audio_base64}",
    }


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form("hi")) -> dict:
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio payload is empty.")

    suffix = Path(audio.filename or "input.webm").suffix or ".webm"
    transcript = transcribe_audio(audio_bytes, language="hi", source_suffix=suffix)
    if not transcript:
        raise HTTPException(status_code=400, detail="Could not transcribe audio.")

    _debug_print("Transcript:", transcript)
    return {"transcript": transcript, "language": language}


@app.post("/api/intent")
def detect_intent(payload: IntentRequest) -> dict:
    intent, confidence = predict_intent(payload.text)
    _debug_print("Detected intent:", intent)
    _debug_print("Confidence:", confidence)
    return {
        "intent": intent,
        "confidence": round(float(confidence) * 100.0, 2),
    }


@app.post("/api/tts")
def synthesize(payload: TTSRequest) -> dict:
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text payload is empty.")

    audio_base64 = generate_tts(text, payload.language)
    if not audio_base64:
        raise HTTPException(status_code=500, detail="TTS generation failed.")

    return {"audio_base64": f"data:audio/mp3;base64,{audio_base64}"}


@app.post("/api/process-text")
def process_text(
    text: str = Form(...),
    user_id: str = Form(...),
    language: str = Form("en"),
) -> dict:
    transcript = (text or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Text payload is empty.")

    _debug_print("Frontend transcript:", transcript)
    return _process_transcript(transcript=transcript, user_id=user_id, language=language)


@app.post("/api/process-audio")
async def process_audio(
    audio: Optional[UploadFile] = File(None),
    text: str = Form(""),
    user_id: str = Form(...),
    language: str = Form("en"),
) -> dict:
    try:
        transcript = (text or "").strip()
        if transcript:
            _debug_print("Frontend transcript:", transcript)
            return _process_transcript(transcript=transcript, user_id=user_id, language=language)

        if audio is None:
            raise HTTPException(status_code=400, detail="Either text or audio is required.")

        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio payload is empty.")

        suffix = Path(audio.filename or "input.webm").suffix or ".webm"
        transcript = transcribe_audio(audio_bytes, language="hi", source_suffix=suffix)
        if not transcript:
            raise HTTPException(status_code=400, detail="Could not transcribe audio.")
        _debug_print("Transcript:", transcript)

        return _process_transcript(transcript=transcript, user_id=user_id, language=language)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
