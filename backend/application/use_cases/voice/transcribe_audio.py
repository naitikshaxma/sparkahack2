from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException


async def transcribe_audio(
    *,
    audio_bytes: bytes,
    filename: str,
    body_language: Optional[str],
    header_language: Optional[str],
    stt_service: Any,
    timings: Optional[Dict[str, Any]],
    resolve_request_language_fn: Callable[[Optional[str], Optional[str]], str],
    resolve_auto_language_fn: Callable[[Optional[str], Optional[str], str], str],
) -> Dict[str, Any]:
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio payload is empty.")

    suffix = Path(filename or "input.webm").suffix or ".webm"
    request_language = resolve_request_language_fn(body_language, header_language)
    transcript = await stt_service.transcribe_async(
        audio_bytes=audio_bytes,
        language=request_language,
        suffix=suffix,
        timings=timings or {},
    )
    request_language = resolve_auto_language_fn(body_language, header_language, transcript)
    if not transcript:
        raise HTTPException(status_code=400, detail="Could not transcribe audio.")

    return {
        "transcript": transcript,
        "language": request_language,
        "response_text": transcript,
        "user_input_length": len(audio_bytes),
    }
