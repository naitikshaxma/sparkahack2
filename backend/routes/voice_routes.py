import json
import logging
import os
import subprocess
import tempfile
import uuid
import asyncio
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError

from ..container import inject_container
from ..models.api_models import AutofillRequest, ResetSessionRequest, TTSRequest
from ..logger import log_event
from ..tts_service import split_tts_chunks
from ..utils.language import detect_input_language, detect_text_language, normalize_language_code
from ..utils.personality import apply_tone, normalize_tone
from ..utils.privacy import redact_sensitive_text, sanitize_profile_for_response
from ..utils.session_manager import create_session, delete_session, get_session, update_session
from ..voice_analytics import record_interruption, record_latency_perception, record_retry, record_stt_signal, snapshot
from ..voice_state import clear_interrupt, get_voice_state, interrupt_voice, is_interrupted, set_voice_state
from .response_utils import standardized_success


router = APIRouter(tags=["voice"])
logger = logging.getLogger(__name__)

MAX_OCR_FILE_BYTES = 5 * 1024 * 1024
ALLOWED_OCR_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
ALLOWED_OCR_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _base_response(
    session_id: str = "",
    response_text: str = "",
    field_name: Optional[str] = None,
    validation_passed: bool = True,
    validation_error: Optional[str] = None,
    session_complete: bool = False,
    mode: str = "action",
    action: Optional[str] = None,
    steps_done: int = 0,
    steps_total: int = 0,
    completed_fields: Optional[list] = None,
    scheme_details: Optional[dict] = None,
    recommended_schemes: Optional[list] = None,
    user_profile: Optional[dict] = None,
    quick_actions: Optional[list] = None,
    voice_text: Optional[str] = None,
) -> dict:
    return {
        "session_id": session_id,
        "response_text": response_text,
        "field_name": field_name,
        "validation_passed": validation_passed,
        "validation_error": validation_error,
        "session_complete": session_complete,
        "mode": mode,
        "action": action,
        "steps_done": steps_done,
        "steps_total": steps_total,
        "completed_fields": completed_fields or [],
        "scheme_details": scheme_details,
        "recommended_schemes": recommended_schemes or [],
        "user_profile": user_profile or {},
        "quick_actions": quick_actions or [],
        "voice_text": voice_text,
    }


def _resolve_request_language(body_language: Optional[str], header_language: Optional[str]) -> str:
    provided = (body_language or "").strip() or (header_language or "").strip()
    return normalize_language_code(provided, default="en")


def _resolve_auto_language(body_language: Optional[str], header_language: Optional[str], text_hint: str = "") -> str:
    provided = (body_language or "").strip() or (header_language or "").strip()
    if provided:
        return normalize_language_code(provided, default="en")
    return detect_input_language(text_hint, default="en")


def _lang_text(language: str, en_text: str, hi_text: str) -> str:
    return hi_text if normalize_language_code(language, default="en") == "hi" else en_text


def _validate_session_id(session_id: str, max_len: int) -> str:
    cleaned = (session_id or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="session_id is required")
    if len(cleaned) > max_len:
        raise HTTPException(status_code=400, detail="session_id is too long")
    return cleaned


def _stt_signal_score(transcript: str) -> float:
    content = (transcript or "").strip()
    if not content:
        return 0.0
    if len(content) < 4:
        return 0.2
    if len(content) < 12:
        return 0.55
    return 0.9


@router.post("/transcribe")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(""),
    x_language: Optional[str] = Header(None, alias="x-language"),
    container=Depends(inject_container),
):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio payload is empty.")

    suffix = Path(audio.filename or "input.webm").suffix or ".webm"
    request_language = _resolve_request_language(language, x_language)
    timings = getattr(request.state, "timings", {})
    transcript = await container.stt_service.transcribe_async(audio_bytes=audio_bytes, language=request_language, suffix=suffix, timings=timings)
    request_language = _resolve_auto_language(language, x_language, transcript)
    if not transcript:
        raise HTTPException(status_code=400, detail="Could not transcribe audio.")
    request.state.user_input_length = len(audio_bytes)

    return standardized_success({
        **_base_response(response_text=transcript),
        "transcript": transcript,
        "language": request_language,
    })


@router.post("/tts")
async def synthesize(payload: TTSRequest, request: Request, x_language: Optional[str] = Header(None, alias="x-language"), container=Depends(inject_container)):
    client_ip = request.client.host if request.client else "unknown"
    validation = container.input_validator.validate_input(payload.text, client_ip=client_ip, endpoint=request.url.path)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid input.")
    text = validation.sanitized_text
    request_language = _resolve_auto_language(payload.language, x_language, text)
    timings = getattr(request.state, "timings", {})
    tone = normalize_tone(payload.tone or container.settings.response_tone, default=container.settings.response_tone)
    toned_text = apply_tone(text, tone, request_language)
    session_key = (payload.session_id or "").strip()
    if session_key:
        if is_interrupted(session_key):
            clear_interrupt(session_key)
        set_voice_state(session_key, "speaking")
    try:
        audio_base64 = await container.tts_service.synthesize_async(text=toned_text, language=request_language, timings=timings)
        if not audio_base64:
            raise HTTPException(status_code=500, detail="TTS generation failed.")
        request.state.user_input_length = len(validation.normalized_text)
    finally:
        if session_key:
            set_voice_state(session_key, "idle")

    return standardized_success({
        **_base_response(response_text=toned_text),
        "audio_base64": f"data:audio/mp3;base64,{audio_base64}",
    })


@router.post("/tts-stream")
async def synthesize_stream(payload: TTSRequest, request: Request, x_language: Optional[str] = Header(None, alias="x-language"), container=Depends(inject_container)):
    client_ip = request.client.host if request.client else "unknown"
    validation = container.input_validator.validate_input(payload.text, client_ip=client_ip, endpoint=request.url.path)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid input.")

    text = validation.sanitized_text
    request_language = _resolve_auto_language(payload.language, x_language, text)
    tone = normalize_tone(payload.tone or container.settings.response_tone, default=container.settings.response_tone)
    toned_text = apply_tone(text, tone, request_language)
    timings = getattr(request.state, "timings", {})
    session_key = (payload.session_id or "").strip()

    if session_key:
        if is_interrupted(session_key):
            clear_interrupt(session_key)
        set_voice_state(session_key, "speaking")

    async def _iter_audio():
        try:
            async for chunk in container.tts_service.stream_synthesize_async(
                toned_text,
                request_language,
                interrupted=(lambda: is_interrupted(session_key)) if session_key else None,
                timings=timings,
            ):
                yield chunk
                await asyncio.sleep(0)
        finally:
            if session_key:
                set_voice_state(session_key, "idle")

    return StreamingResponse(_iter_audio(), media_type="audio/mpeg")


@router.post("/tts-interrupt")
def tts_interrupt(session_id: str = Form("")):
    resolved_session_id = (session_id or "").strip()
    if not resolved_session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    interrupt_voice(resolved_session_id)
    record_interruption(resolved_session_id)
    set_voice_state(resolved_session_id, "interrupted")
    return standardized_success({
        "session_id": resolved_session_id,
        "interrupted": True,
        "state": "interrupted",
    })


@router.get("/voice-state")
def voice_state(session_id: str):
    resolved_session_id = (session_id or "").strip()
    if not resolved_session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    current = get_voice_state(resolved_session_id)
    return standardized_success({
        "session_id": resolved_session_id,
        "state": current.get("state", "idle"),
        "interrupted": bool(current.get("interrupted", False)),
    })


@router.get("/voice-analytics")
def voice_analytics(session_id: Optional[str] = None):
    return standardized_success(snapshot(session_id))


@router.post("/process-text")
async def process_text(
    request: Request,
    text: str = Form(""),
    user_id: str = Form(""),
    session_id: str = Form(""),
    language: str = Form(""),
    x_language: Optional[str] = Header(None, alias="x-language"),
    debug: bool = Query(False),
    container=Depends(inject_container),
):
    client_ip = request.client.host if request.client else "unknown"
    validation = container.input_validator.validate_input(text, client_ip=client_ip, endpoint=request.url.path)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid input.")
    transcript = validation.sanitized_text
    request.state.user_input_length = len(validation.normalized_text)
    request_language = _resolve_auto_language(language, x_language, transcript)
    timings = getattr(request.state, "timings", {})

    resolved_session_id = (session_id or user_id or "").strip() or str(uuid.uuid4())
    resolved_session_id = _validate_session_id(resolved_session_id, container.settings.max_session_id_chars)
    try:
        get_session(resolved_session_id)
    except Exception:
        create_session(resolved_session_id)

    if is_interrupted(resolved_session_id):
        clear_interrupt(resolved_session_id)
    set_voice_state(resolved_session_id, "processing")
    start = time.perf_counter()
    try:
        intent_task = asyncio.create_task(container.intent_service.detect_async(transcript, debug=False, timings=timings))
        conversation_result = await asyncio.to_thread(
            container.conversation_service.process,
            resolved_session_id,
            transcript,
            request_language,
            debug,
        )

        tts_text = conversation_result.get("voice_text") or conversation_result["response_text"]
        if detect_text_language(tts_text, default=request_language) != request_language:
            tts_text = conversation_result["response_text"]
        tone = normalize_tone(container.settings.response_tone, default=container.settings.response_tone)
        tts_text = apply_tone(tts_text, tone, request_language)
        set_voice_state(resolved_session_id, "speaking")
        audio_base64 = await container.tts_service.synthesize_async(tts_text, request_language, timings=timings)
        intent_signal = await intent_task
        request.state.intent = conversation_result.get("primary_intent")
        request.state.confidence = (conversation_result.get("intent_debug") or {}).get("confidence")
        if isinstance(intent_signal, dict):
            timings["intent_signal_confidence"] = intent_signal.get("confidence")
        record_latency_perception(resolved_session_id, (time.perf_counter() - start) * 1000.0)
        if not conversation_result.get("validation_passed", True):
            record_retry(resolved_session_id)
    finally:
        set_voice_state(resolved_session_id, "idle")

    response = {
        **_base_response(
            session_id=resolved_session_id,
            response_text=conversation_result["response_text"],
            field_name=conversation_result.get("field_name"),
            validation_passed=conversation_result.get("validation_passed", True),
            validation_error=conversation_result.get("validation_error"),
            session_complete=conversation_result["session_complete"],
            mode=conversation_result.get("mode", "action"),
            action=conversation_result.get("action"),
            steps_done=conversation_result.get("steps_done", 0),
            steps_total=conversation_result.get("steps_total", 0),
            completed_fields=conversation_result.get("completed_fields", []),
            scheme_details=conversation_result.get("scheme_details"),
            recommended_schemes=conversation_result.get("recommended_schemes", []),
            user_profile=sanitize_profile_for_response(conversation_result.get("user_profile", {})),
            quick_actions=conversation_result.get("quick_actions", []),
            voice_text=tts_text,
        ),
        "audio_base64": f"data:audio/mp3;base64,{audio_base64}" if audio_base64 else None,
        "primary_intent": conversation_result.get("primary_intent"),
        "secondary_intents": conversation_result.get("secondary_intents", []),
    }

    if debug:
        response["debug"] = {
            "raw_model_output": (conversation_result.get("intent_debug") or {}).get("raw_model_output"),
            "normalized_intent": (conversation_result.get("intent_debug") or {}).get("normalized_intent"),
            "confidence": (conversation_result.get("intent_debug") or {}).get("confidence"),
            "fallback_used": (conversation_result.get("intent_debug") or {}).get("fallback_used"),
            "context_used": (conversation_result.get("intent_debug") or {}).get("context_used"),
            "normalized_input": validation.normalized_text,
            "processing_times": timings,
        }

    return standardized_success(response)


@router.post("/process-text-stream")
async def process_text_stream(
    request: Request,
    text: str = Form(""),
    user_id: str = Form(""),
    session_id: str = Form(""),
    language: str = Form(""),
    x_language: Optional[str] = Header(None, alias="x-language"),
    debug: bool = Query(False),
    container=Depends(inject_container),
):
    client_ip = request.client.host if request.client else "unknown"
    validation = container.input_validator.validate_input(text, client_ip=client_ip, endpoint=request.url.path)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid input.")
    transcript = validation.sanitized_text
    request.state.user_input_length = len(validation.normalized_text)
    request_language = _resolve_auto_language(language, x_language, transcript)
    timings = getattr(request.state, "timings", {})

    resolved_session_id = (session_id or user_id or "").strip() or str(uuid.uuid4())
    resolved_session_id = _validate_session_id(resolved_session_id, container.settings.max_session_id_chars)
    try:
        get_session(resolved_session_id)
    except Exception:
        create_session(resolved_session_id)

    if is_interrupted(resolved_session_id):
        clear_interrupt(resolved_session_id)
    set_voice_state(resolved_session_id, "processing")

    intent_task = asyncio.create_task(container.intent_service.detect_async(transcript, debug=False, timings=timings))
    conversation_result = await asyncio.to_thread(
        container.conversation_service.process,
        resolved_session_id,
        transcript,
        request_language,
        debug,
    )
    _ = await intent_task
    request.state.intent = conversation_result.get("primary_intent")
    request.state.confidence = (conversation_result.get("intent_debug") or {}).get("confidence")

    tts_text = conversation_result.get("voice_text") or conversation_result["response_text"]
    if detect_text_language(tts_text, default=request_language) != request_language:
        tts_text = conversation_result["response_text"]
    tone = normalize_tone(container.settings.response_tone, default=container.settings.response_tone)
    tts_text = apply_tone(tts_text, tone, request_language)

    meta = {
        **_base_response(
            session_id=resolved_session_id,
            response_text=conversation_result["response_text"],
            field_name=conversation_result.get("field_name"),
            validation_passed=conversation_result.get("validation_passed", True),
            validation_error=conversation_result.get("validation_error"),
            session_complete=conversation_result["session_complete"],
            mode=conversation_result.get("mode", "action"),
            action=conversation_result.get("action"),
            steps_done=conversation_result.get("steps_done", 0),
            steps_total=conversation_result.get("steps_total", 0),
            completed_fields=conversation_result.get("completed_fields", []),
            scheme_details=conversation_result.get("scheme_details"),
            recommended_schemes=conversation_result.get("recommended_schemes", []),
            user_profile=sanitize_profile_for_response(conversation_result.get("user_profile", {})),
            quick_actions=conversation_result.get("quick_actions", []),
            voice_text=tts_text,
        ),
        "primary_intent": conversation_result.get("primary_intent"),
        "secondary_intents": conversation_result.get("secondary_intents", []),
    }

    chunk_texts = split_tts_chunks(tts_text)

    async def _iter_events():
        first_chunk_started_at = time.perf_counter()
        try:
            if not conversation_result.get("validation_passed", True):
                record_retry(resolved_session_id)
            yield json.dumps({"type": "meta", "payload": meta}, ensure_ascii=False) + "\n"
            set_voice_state(resolved_session_id, "speaking")
            for index, chunk_text in enumerate(chunk_texts):
                if is_interrupted(resolved_session_id):
                    yield json.dumps({"type": "interrupted", "session_id": resolved_session_id}, ensure_ascii=False) + "\n"
                    break
                try:
                    chunk_b64 = await container.tts_service.synthesize_async(chunk_text, request_language, timings=timings)
                except Exception as exc:
                    log_event(
                        "stream_tts_chunk_error",
                        level="warning",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="failure",
                        error_type=type(exc).__name__,
                        session_id=resolved_session_id,
                        chunk_index=index,
                    )
                    continue
                if not chunk_b64:
                    continue
                if index == 0:
                    record_latency_perception(resolved_session_id, (time.perf_counter() - first_chunk_started_at) * 1000.0)
                payload = {
                    "type": "audio_chunk",
                    "seq": index,
                    "text_segment": chunk_text,
                    "audio_base64": chunk_b64,
                }
                yield json.dumps(payload, ensure_ascii=False) + "\n"
                await asyncio.sleep(0)
            yield json.dumps({"type": "done", "session_id": resolved_session_id}, ensure_ascii=False) + "\n"
        finally:
            set_voice_state(resolved_session_id, "idle")

    return StreamingResponse(_iter_events(), media_type="application/x-ndjson")


@router.post("/process-audio")
async def process_audio(
    request: Request,
    audio: Optional[UploadFile] = File(None),
    text: str = Form(""),
    user_id: str = Form(""),
    session_id: str = Form(""),
    language: str = Form(""),
    x_language: Optional[str] = Header(None, alias="x-language"),
    debug: bool = Query(False),
    container=Depends(inject_container),
):
    client_ip = request.client.host if request.client else "unknown"
    request_language = _resolve_request_language(language, x_language)
    timings = getattr(request.state, "timings", {})
    resolved_session_id = (session_id or user_id or "").strip() or str(uuid.uuid4())
    resolved_session_id = _validate_session_id(resolved_session_id, container.settings.max_session_id_chars)
    try:
        get_session(resolved_session_id)
    except Exception:
        create_session(resolved_session_id)

    transcript = (text or "").strip()
    if is_interrupted(resolved_session_id):
        clear_interrupt(resolved_session_id)
    set_voice_state(resolved_session_id, "processing")

    if transcript:
        validation = container.input_validator.validate_input(transcript, client_ip=client_ip, endpoint=request.url.path)
        if not validation.is_valid:
            raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid input.")
        transcript = validation.sanitized_text
        request.state.user_input_length = len(validation.normalized_text)
        request_language = _resolve_auto_language(language, x_language, transcript)
        record_stt_signal(resolved_session_id, _stt_signal_score(transcript))
    else:
        if audio is None:
            raise HTTPException(status_code=400, detail="Either text or audio is required.")
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio payload is empty.")
        suffix = Path(audio.filename or "input.webm").suffix or ".webm"
        transcript = await container.stt_service.transcribe_async(audio_bytes=audio_bytes, language=request_language, suffix=suffix, timings=timings)
        request_language = _resolve_auto_language(language, x_language, transcript)
        validation = container.input_validator.validate_input(transcript, client_ip=client_ip, endpoint=request.url.path)
        if not validation.is_valid:
            raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid transcript.")
        transcript = validation.sanitized_text
        request.state.user_input_length = len(validation.normalized_text)
        record_stt_signal(resolved_session_id, _stt_signal_score(transcript))

    start = time.perf_counter()
    try:
        intent_task = asyncio.create_task(container.intent_service.detect_async(transcript, debug=False, timings=timings))
        conversation_result = await asyncio.to_thread(
            container.conversation_service.process,
            resolved_session_id,
            transcript,
            request_language,
            debug,
        )

        tts_text = conversation_result.get("voice_text") or conversation_result["response_text"]
        if detect_text_language(tts_text, default=request_language) != request_language:
            tts_text = conversation_result["response_text"]
        tone = normalize_tone(container.settings.response_tone, default=container.settings.response_tone)
        tts_text = apply_tone(tts_text, tone, request_language)
        set_voice_state(resolved_session_id, "speaking")
        audio_base64 = await container.tts_service.synthesize_async(tts_text, request_language, timings=timings)
        _ = await intent_task
        request.state.intent = conversation_result.get("primary_intent")
        request.state.confidence = (conversation_result.get("intent_debug") or {}).get("confidence")
        record_latency_perception(resolved_session_id, (time.perf_counter() - start) * 1000.0)
        if not conversation_result.get("validation_passed", True):
            record_retry(resolved_session_id)
    finally:
        set_voice_state(resolved_session_id, "idle")

    response = {
        **_base_response(
            session_id=resolved_session_id,
            response_text=conversation_result["response_text"],
            field_name=conversation_result.get("field_name"),
            validation_passed=conversation_result.get("validation_passed", True),
            validation_error=conversation_result.get("validation_error"),
            session_complete=conversation_result["session_complete"],
            mode=conversation_result.get("mode", "action"),
            action=conversation_result.get("action"),
            steps_done=conversation_result.get("steps_done", 0),
            steps_total=conversation_result.get("steps_total", 0),
            completed_fields=conversation_result.get("completed_fields", []),
            scheme_details=conversation_result.get("scheme_details"),
            recommended_schemes=conversation_result.get("recommended_schemes", []),
            user_profile=sanitize_profile_for_response(conversation_result.get("user_profile", {})),
            quick_actions=conversation_result.get("quick_actions", []),
            voice_text=tts_text,
        ),
        "transcript": transcript,
        "audio_base64": f"data:audio/mp3;base64,{audio_base64}" if audio_base64 else None,
        "primary_intent": conversation_result.get("primary_intent"),
        "secondary_intents": conversation_result.get("secondary_intents", []),
    }

    if debug:
        response["debug"] = {
            "raw_model_output": (conversation_result.get("intent_debug") or {}).get("raw_model_output"),
            "normalized_intent": (conversation_result.get("intent_debug") or {}).get("normalized_intent"),
            "confidence": (conversation_result.get("intent_debug") or {}).get("confidence"),
            "fallback_used": (conversation_result.get("intent_debug") or {}).get("fallback_used"),
            "context_used": (conversation_result.get("intent_debug") or {}).get("context_used"),
            "normalized_input": validation.normalized_text,
            "processing_times": timings,
        }

    return standardized_success(response)


@router.post("/ocr")
async def process_ocr(
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    language: str = Form(""),
    x_language: Optional[str] = Header(None, alias="x-language"),
    container=Depends(inject_container),
):
    resolved_session_id = _validate_session_id(session_id, container.settings.max_session_id_chars)
    request_language = _resolve_request_language(language, x_language)
    timings = getattr(request.state, "timings", {})
    if is_interrupted(resolved_session_id):
        clear_interrupt(resolved_session_id)
    set_voice_state(resolved_session_id, "processing")

    fallback_data = {
        "full_name": None,
        "aadhaar_number": None,
        "date_of_birth": None,
        "address": None,
        "confidence": 0.0,
    }
    temp_path: Optional[str] = None

    try:
        session = get_session(resolved_session_id)
        session["language"] = request_language

        suffix = Path(file.filename or "document.png").suffix.lower() or ".png"
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_OCR_MIME_TYPES or suffix not in ALLOWED_OCR_SUFFIXES:
            return standardized_success({
                "session_id": resolved_session_id,
                "response_text": _lang_text(request_language, "Please upload a valid image file.", "कृपया मान्य चित्र फ़ाइल अपलोड करें।"),
                "field_name": None,
                "validation_passed": False,
                "validation_error": "invalid_file_type",
                "ocr_data": fallback_data,
                "session_complete": False,
            })

        file_bytes = await file.read()
        request.state.user_input_length = len(file_bytes)
        if len(file_bytes) > MAX_OCR_FILE_BYTES:
            return standardized_success({
                "session_id": resolved_session_id,
                "response_text": _lang_text(request_language, "Please upload a file smaller than 5 MB.", "कृपया 5 एमबी से छोटी फ़ाइल अपलोड करें।"),
                "field_name": None,
                "validation_passed": False,
                "validation_error": "file_too_large",
                "ocr_data": fallback_data,
                "session_complete": False,
            })

        if not file_bytes:
            return standardized_success({
                "session_id": resolved_session_id,
                "response_text": _lang_text(request_language, "The image is unclear. Please try again.", "चित्र स्पष्ट नहीं है। कृपया फिर से प्रयास करें।"),
                "field_name": None,
                "validation_passed": False,
                "validation_error": "empty_file",
                "ocr_data": fallback_data,
                "session_complete": False,
            })

        try:
            with Image.open(BytesIO(file_bytes)) as img:
                img.verify()
        except (UnidentifiedImageError, OSError, ValueError):
            return standardized_success({
                "session_id": resolved_session_id,
                "response_text": _lang_text(request_language, "Please upload a valid image file.", "कृपया मान्य चित्र फ़ाइल अपलोड करें।"),
                "field_name": None,
                "validation_passed": False,
                "validation_error": "invalid_image_payload",
                "ocr_data": fallback_data,
                "session_complete": False,
            })

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        ocr_text = await container.ocr_service.extract_text_async(temp_path, timings=timings)
        if not (ocr_text or "").strip():
            return standardized_success({
                "session_id": resolved_session_id,
                "response_text": _lang_text(request_language, "The image is unclear. Please try again.", "चित्र स्पष्ट नहीं है। कृपया फिर से प्रयास करें।"),
                "field_name": None,
                "validation_passed": False,
                "validation_error": "ocr_text_empty",
                "ocr_data": fallback_data,
                "session_complete": False,
            })

        ocr_data = await container.ocr_service.extract_structured_data_async(ocr_text, timings=timings)
        if isinstance(timings, dict) and "ocr_text_extraction_ms" in timings and "ocr_structuring_ms" in timings:
            timings["ocr_processing_ms"] = round(float(timings["ocr_text_extraction_ms"]) + float(timings["ocr_structuring_ms"]), 2)
        confidence = float(ocr_data.get("confidence") or 0.0)
        if confidence < 0.6:
            return standardized_success({
                "session_id": resolved_session_id,
                "response_text": _lang_text(request_language, "The document is unclear. Please scan again.", "दस्तावेज़ स्पष्ट नहीं है। कृपया फिर से स्कैन करें।"),
                "field_name": None,
                "validation_passed": False,
                "validation_error": "low_ocr_confidence",
                "ocr_data": ocr_data,
                "session_complete": False,
            })

        session = get_session(resolved_session_id)
        session["language"] = request_language
        session = container.conversation_service.merge_ocr(session, ocr_data)

        extracted_fields = session.get("ocr_extracted", {}).get("fields", [])
        if not extracted_fields:
            update_session(resolved_session_id, session)
            return standardized_success({
                "session_id": resolved_session_id,
                "response_text": _lang_text(request_language, "The image is unclear. Please try again.", "चित्र स्पष्ट नहीं है। कृपया फिर से प्रयास करें।"),
                "field_name": None,
                "validation_passed": False,
                "validation_error": "ocr_merge_empty",
                "ocr_data": ocr_data,
                "session_complete": False,
            })

        message = container.conversation_service.ocr_confirmation(session, ocr_data, session.get("language", "en"))
        if len(extracted_fields) < 2:
            prefix = _lang_text(
                request_language,
                f"I scanned a few details: {', '.join(extracted_fields)}. Please share the remaining details.",
                f"मैंने कुछ विवरण स्कैन किए हैं: {', '.join(extracted_fields)}। कृपया शेष विवरण बताएं।",
            )
            message = f"{prefix}\n{message}"

        session.setdefault("conversation_history", []).append({"role": "assistant", "content": redact_sensitive_text(message)})
        session["conversation_history"] = session["conversation_history"][-10:]
        update_session(resolved_session_id, session)

        return standardized_success({
            "session_id": resolved_session_id,
            "response_text": message,
            "field_name": session.get("next_field"),
            "validation_passed": True,
            "validation_error": None,
            "ocr_data": ocr_data,
            "session_complete": False,
        })
    finally:
        set_voice_state(resolved_session_id, "idle")
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


@router.post("/autofill")
def trigger_autofill(payload: AutofillRequest):
    session_id = (payload.session_id or "").strip()
    if not session_id:
        return standardized_success({
            **_base_response(session_id="", response_text="session_id is required", validation_passed=False, validation_error="missing_session_id", session_complete=False),
            "status": "autofill_not_started",
        })

    session = get_session(session_id)
    if not session:
        return standardized_success({
            **_base_response(session_id=session_id, response_text="Session not found", validation_passed=False, validation_error="session_not_found", session_complete=False),
            "status": "autofill_not_started",
        })

    if not session.get("session_complete", False):
        return standardized_success({
            **_base_response(session_id=session_id, response_text="Session not complete yet", validation_passed=False, validation_error="session_not_complete", session_complete=False),
            "status": "autofill_not_started",
        })

    temp_dir = Path(tempfile.gettempdir())
    payload_path = temp_dir / f"autofill_{session_id}.json"
    payload_path.write_text(json.dumps(session), encoding="utf-8")

    script_path = Path(__file__).resolve().parents[1] / "automation" / "autofill_service.js"
    subprocess.Popen(
        ["node", str(script_path), str(payload_path)],
        cwd=str(Path(__file__).resolve().parents[2]),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return standardized_success({
        **_base_response(session_id=session_id, response_text="autofill_started", validation_passed=True, validation_error=None, session_complete=True),
        "status": "autofill_started",
    })


@router.post("/reset-session")
def reset_session(payload: ResetSessionRequest):
    session_id = (payload.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    delete_session(session_id)
    create_session(session_id)
    return standardized_success({"status": "reset", "session_id": session_id})
