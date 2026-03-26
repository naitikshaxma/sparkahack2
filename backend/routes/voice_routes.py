import contextlib
import json
import logging
import os
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

from ..application.use_cases.voice.synthesize_tts import synthesize_tts as synthesize_tts_use_case
from ..application.use_cases.voice.transcribe_audio import transcribe_audio as transcribe_audio_use_case
from ..container import inject_container
from ..metrics import record_automation_result, record_timing
from ..models.api_models import AutofillRequest, ResetSessionRequest, TTSRequest
from ..logger import log_event
from ..tts_service import split_tts_chunks
from ..utils.language import detect_input_language, detect_text_language, normalize_language_code
from ..utils.personality import apply_tone, normalize_tone
from ..utils.privacy import redact_sensitive_text, sanitize_profile_for_response
from ..utils.rate_limit import allow_request
from ..utils.session_manager import create_session, delete_session, get_async_session_lock, get_session, update_session
from ..voice_analytics import record_interruption, record_latency_perception, record_retry, record_stt_signal, snapshot
from ..voice_state import begin_stream, clear_interrupt, end_stream, get_voice_state, interrupt_voice, is_interrupted, is_stream_active, set_voice_state
from .response_utils import standardized_success


router = APIRouter(tags=["voice"])
logger = logging.getLogger(__name__)

MAX_OCR_FILE_BYTES = 5 * 1024 * 1024
ALLOWED_OCR_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
ALLOWED_OCR_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
STREAM_CHUNK_DELAY_MS = max(0, int((os.getenv("STREAM_CHUNK_DELAY_MS") or "0").strip() or "0"))
STREAM_MAX_DURATION_SECONDS = max(5, int((os.getenv("STREAM_MAX_DURATION_SECONDS") or "120").strip() or "120"))
SESSION_RATE_LIMIT_WINDOW_SECONDS = max(10, int((os.getenv("SESSION_RATE_LIMIT_WINDOW_SECONDS") or "60").strip() or "60"))
SESSION_RATE_LIMIT_MAX_REQUESTS = max(5, int((os.getenv("SESSION_RATE_LIMIT_MAX_REQUESTS") or "50").strip() or "50"))


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


def _enforce_session_rate_limit(session_id: str, user_id: str) -> None:
    session_key = (session_id or "").strip()
    user_key = (user_id or "").strip()
    limiter_key = f"session:{session_key or user_key or 'anonymous'}"
    allowed = allow_request(
        limiter_key,
        max_requests=SESSION_RATE_LIMIT_MAX_REQUESTS,
        window_seconds=SESSION_RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many requests for this session. Please retry shortly.")


@router.post("/transcribe")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(""),
    x_language: Optional[str] = Header(None, alias="x-language"),
    container=Depends(inject_container),
):
    audio_bytes = await audio.read()
    timings = getattr(request.state, "timings", {})
    result = await transcribe_audio_use_case(
        audio_bytes=audio_bytes,
        filename=audio.filename or "input.webm",
        body_language=language,
        header_language=x_language,
        stt_service=container.stt_service,
        timings=timings,
        resolve_request_language_fn=_resolve_request_language,
        resolve_auto_language_fn=_resolve_auto_language,
    )
    request.state.user_input_length = result["user_input_length"]

    return standardized_success({
        **_base_response(response_text=result["response_text"]),
        "transcript": result["transcript"],
        "language": result["language"],
    })


@router.post("/tts")
async def synthesize(payload: TTSRequest, request: Request, x_language: Optional[str] = Header(None, alias="x-language"), container=Depends(inject_container)):
    client_ip = request.client.host if request.client else "unknown"
    validation = container.input_validator.validate_input(payload.text, client_ip=client_ip, endpoint=request.url.path)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid input.")
    timings = getattr(request.state, "timings", {})
    result = await synthesize_tts_use_case(
        text=validation.sanitized_text,
        normalized_text=validation.normalized_text,
        body_language=payload.language,
        header_language=x_language,
        tone=payload.tone,
        session_id=payload.session_id,
        default_tone=container.settings.response_tone,
        tts_service=container.tts_service,
        timings=timings,
        resolve_auto_language_fn=_resolve_auto_language,
    )
    request.state.user_input_length = result["user_input_length"]

    return standardized_success({
        **_base_response(response_text=result["response_text"]),
        "audio_base64": result["audio_base64"],
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
        stream_generation = begin_stream(session_key)
    else:
        stream_generation = None

    async def _iter_audio():
        stream_start = time.perf_counter()
        stream_deadline = stream_start + STREAM_MAX_DURATION_SECONDS
        end_reason = "completed"
        log_event(
            "stream_start",
            request_id=getattr(request.state, "request_id", ""),
            endpoint=request.url.path,
            status="success",
            session_id=session_key,
            stream="tts_stream",
        )
        semaphore_acquired = False
        try:
            try:
                await asyncio.wait_for(
                    request.app.state.concurrency_semaphore.acquire(),
                    timeout=request.app.state.concurrency_timeout_seconds,
                )
                semaphore_acquired = True
            except asyncio.TimeoutError:
                end_reason = "concurrency_limit"
                log_event(
                    "concurrency_limit_reached",
                    level="warning",
                    request_id=getattr(request.state, "request_id", ""),
                    endpoint=request.url.path,
                    status="failure",
                    error_type="concurrency_limit_reached",
                    session_id=session_key,
                )
                return
            def _should_interrupt() -> bool:
                if not session_key:
                    return False
                if stream_generation is not None and not is_stream_active(session_key, stream_generation):
                    return True
                return is_interrupted(session_key)

            async for chunk in container.tts_service.stream_synthesize_async(
                toned_text,
                request_language,
                interrupted=_should_interrupt if session_key else None,
                timings=timings,
            ):
                if time.perf_counter() > stream_deadline:
                    end_reason = "timeout"
                    log_event(
                        "stream_timeout",
                        level="warning",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="failure",
                        error_type="stream_timeout",
                        session_id=session_key,
                    )
                    break
                if await request.is_disconnected():
                    end_reason = "client_disconnected"
                    log_event(
                        "tts_stream_client_disconnected",
                        level="warning",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="failure",
                        error_type="client_disconnected",
                        session_id=session_key,
                    )
                    break
                yield chunk
                if STREAM_CHUNK_DELAY_MS > 0:
                    await asyncio.sleep(STREAM_CHUNK_DELAY_MS / 1000.0)
                else:
                    await asyncio.sleep(0)
            if end_reason == "completed" and _should_interrupt():
                end_reason = "interrupted"
                log_event(
                    "stream_interrupted",
                    level="info",
                    request_id=getattr(request.state, "request_id", ""),
                    endpoint=request.url.path,
                    status="success",
                    session_id=session_key,
                )
        except Exception as exc:
            end_reason = "error"
            log_event(
                "tts_stream_failure",
                level="error",
                request_id=getattr(request.state, "request_id", ""),
                endpoint=request.url.path,
                status="failure",
                error_type=type(exc).__name__,
                session_id=session_key,
            )
        finally:
            if session_key and stream_generation is not None:
                end_stream(session_key, stream_generation)
            if semaphore_acquired:
                request.app.state.concurrency_semaphore.release()
            log_event(
                "stream_end",
                request_id=getattr(request.state, "request_id", ""),
                endpoint=request.url.path,
                status="success" if end_reason == "completed" else "failure",
                error_type=None if end_reason == "completed" else end_reason,
                session_id=session_key,
                stream="tts_stream",
                duration_ms=round((time.perf_counter() - stream_start) * 1000.0, 2),
            )

    return StreamingResponse(
        _iter_audio(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tts-interrupt")
def tts_interrupt(session_id: str = Form("")):
    resolved_session_id = (session_id or "").strip()
    if not resolved_session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    interrupt_voice(resolved_session_id)
    record_interruption(resolved_session_id)
    set_voice_state(resolved_session_id, "interrupted")
    log_event(
        "tts_interrupt",
        request_id="",
        endpoint="/api/tts-interrupt",
        status="success",
        session_id=resolved_session_id,
    )
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
    route_start = time.perf_counter()
    log_event(
        "voice_process_text_start",
        request_id=getattr(request.state, "request_id", ""),
        endpoint=request.url.path,
        method=request.method,
        status="started",
        user_id=str(getattr(request.state, "user_id", "") or ""),
    )
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
    _enforce_session_rate_limit(resolved_session_id, user_id)
    try:
        get_session(resolved_session_id)
    except Exception:
        create_session(resolved_session_id)

    if is_interrupted(resolved_session_id):
        clear_interrupt(resolved_session_id)
    set_voice_state(resolved_session_id, "processing")
    start = time.perf_counter()
    intent_task = asyncio.create_task(container.intent_service.detect_async(transcript, debug=False, timings=timings))
    try:
        async with get_async_session_lock(resolved_session_id):
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
        try:
            audio_base64 = await container.tts_service.synthesize_async(tts_text, request_language, timings=timings)
        except Exception as exc:
            audio_base64 = None
            log_event(
                "tts_generation_failed",
                level="warning",
                request_id=getattr(request.state, "request_id", ""),
                endpoint=request.url.path,
                status="failure",
                error_type=type(exc).__name__,
                session_id=resolved_session_id,
            )

        try:
            intent_signal = await intent_task
        except Exception as exc:
            intent_signal = {}
            log_event(
                "intent_service_async_failure",
                level="warning",
                request_id=getattr(request.state, "request_id", ""),
                endpoint=request.url.path,
                status="failure",
                error_type=type(exc).__name__,
                session_id=resolved_session_id,
            )

        request.state.intent = conversation_result.get("primary_intent")
        request.state.confidence = (conversation_result.get("intent_debug") or {}).get("confidence")
        if isinstance(intent_signal, dict):
            timings["intent_signal_confidence"] = intent_signal.get("confidence")
        record_latency_perception(resolved_session_id, (time.perf_counter() - start) * 1000.0)
        if not conversation_result.get("validation_passed", True):
            record_retry(resolved_session_id)
    except Exception:
        if not intent_task.done():
            intent_task.cancel()
            try:
                await intent_task
            except Exception:
                pass
        raise
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
        "tts_error": None if audio_base64 else "tts_failed",
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

    response_time_ms = round((time.perf_counter() - route_start) * 1000.0, 2)
    log_event(
        "voice_process_text_success",
        request_id=getattr(request.state, "request_id", ""),
        endpoint=request.url.path,
        method=request.method,
        status="success",
        response_time_ms=response_time_ms,
        user_id=str(getattr(request.state, "user_id", "") or ""),
    )
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
    route_start = time.perf_counter()
    log_event(
        "voice_process_text_stream_start",
        request_id=getattr(request.state, "request_id", ""),
        endpoint=request.url.path,
        method=request.method,
        status="started",
        user_id=str(getattr(request.state, "user_id", "") or ""),
    )
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
    _enforce_session_rate_limit(resolved_session_id, user_id)
    try:
        get_session(resolved_session_id)
    except Exception:
        create_session(resolved_session_id)

    if is_interrupted(resolved_session_id):
        clear_interrupt(resolved_session_id)
    set_voice_state(resolved_session_id, "processing")

    async def _iter_events():
        meta_sent = False
        intent_task: asyncio.Task | None = None
        stream_generation = begin_stream(resolved_session_id)
        disconnected = False
        end_reason = "completed"
        stream_start = time.perf_counter()
        stream_deadline = stream_start + STREAM_MAX_DURATION_SECONDS
        log_event(
            "stream_start",
            request_id=getattr(request.state, "request_id", ""),
            endpoint=request.url.path,
            status="success",
            session_id=resolved_session_id,
            stream="process_text_stream",
        )
        semaphore_acquired = False
        try:
            try:
                await asyncio.wait_for(
                    request.app.state.concurrency_semaphore.acquire(),
                    timeout=request.app.state.concurrency_timeout_seconds,
                )
                semaphore_acquired = True
            except asyncio.TimeoutError:
                end_reason = "concurrency_limit"
                log_event(
                    "concurrency_limit_reached",
                    level="warning",
                    request_id=getattr(request.state, "request_id", ""),
                    endpoint=request.url.path,
                    status="failure",
                    error_type="concurrency_limit_reached",
                    session_id=resolved_session_id,
                )
                if not await request.is_disconnected():
                    error_text = _lang_text(
                        request_language,
                        "The server is busy. Please try again.",
                        "सर्वर व्यस्त है। कृपया फिर से प्रयास करें।",
                    )
                    error_meta = {
                        **_base_response(
                            session_id=resolved_session_id,
                            response_text=error_text,
                            field_name=None,
                            validation_passed=False,
                            validation_error="concurrency_limit",
                            session_complete=False,
                            mode="clarify",
                            action="retry",
                            quick_actions=[],
                            voice_text=error_text,
                        ),
                        "primary_intent": None,
                        "secondary_intents": [],
                    }
                    yield json.dumps({"type": "meta", "payload": error_meta}, ensure_ascii=False) + "\n"
                    meta_sent = True
                return
            if await request.is_disconnected():
                disconnected = True
                end_reason = "client_disconnected"
                return
            intent_task = asyncio.create_task(container.intent_service.detect_async(transcript, debug=False, timings=timings))
            async with get_async_session_lock(resolved_session_id):
                conversation_result = await asyncio.to_thread(
                    container.conversation_service.process,
                    resolved_session_id,
                    transcript,
                    request_language,
                    debug,
                )

            if await request.is_disconnected():
                disconnected = True
                end_reason = "client_disconnected"
                return
            if not is_stream_active(resolved_session_id, stream_generation):
                end_reason = "superseded"
                log_event(
                    "stream_superseded",
                    level="warning",
                    request_id=getattr(request.state, "request_id", ""),
                    endpoint=request.url.path,
                    status="failure",
                    error_type="stream_superseded",
                    session_id=resolved_session_id,
                )
                return
            if time.perf_counter() > stream_deadline:
                end_reason = "timeout"
                log_event(
                    "stream_timeout",
                    level="warning",
                    request_id=getattr(request.state, "request_id", ""),
                    endpoint=request.url.path,
                    status="failure",
                    error_type="stream_timeout",
                    session_id=resolved_session_id,
                )
                error_text = _lang_text(
                    request_language,
                    "The response timed out. Please try again.",
                    "à¤œà¤µà¤¾à¤¬ à¤¦à¥‡à¤° à¤¸à¥‡ à¤†à¤¯à¤¾। à¤•à¥ƒà¤ªà¤¯à¤¾ à¤«à¤¿à¤° à¤¸à¥‡ à¤•à¥‹à¤¶à¤¿à¤¶ à¤•à¤°à¥‡à¤‚।",
                )
                error_meta = {
                    **_base_response(
                        session_id=resolved_session_id,
                        response_text=error_text,
                        field_name=None,
                        validation_passed=False,
                        validation_error="stream_timeout",
                        session_complete=False,
                        mode="clarify",
                        action="retry",
                        quick_actions=[],
                        voice_text=error_text,
                    ),
                    "primary_intent": None,
                    "secondary_intents": [],
                }
                yield json.dumps({"type": "meta", "payload": error_meta}, ensure_ascii=False) + "\n"
                meta_sent = True
                return

            try:
                _ = await intent_task
            except Exception as exc:
                log_event(
                    "intent_service_async_failure",
                    level="warning",
                    request_id=getattr(request.state, "request_id", ""),
                    endpoint=request.url.path,
                    status="failure",
                    error_type=type(exc).__name__,
                    session_id=resolved_session_id,
                )

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

            if not conversation_result.get("validation_passed", True):
                record_retry(resolved_session_id)

            yield json.dumps({"type": "meta", "payload": meta}, ensure_ascii=False) + "\n"
            meta_sent = True

            chunk_texts = split_tts_chunks(tts_text)
            first_chunk_started_at = time.perf_counter()
            set_voice_state(resolved_session_id, "speaking")
            for index, chunk_text in enumerate(chunk_texts):
                if time.perf_counter() > stream_deadline:
                    end_reason = "timeout"
                    log_event(
                        "stream_timeout",
                        level="warning",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="failure",
                        error_type="stream_timeout",
                        session_id=resolved_session_id,
                    )
                    break
                if await request.is_disconnected():
                    disconnected = True
                    end_reason = "client_disconnected"
                    log_event(
                        "stream_client_disconnected",
                        level="warning",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="failure",
                        error_type="client_disconnected",
                        session_id=resolved_session_id,
                    )
                    break
                if is_interrupted(resolved_session_id):
                    end_reason = "interrupted"
                    log_event(
                        "stream_interrupted",
                        level="info",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="success",
                        session_id=resolved_session_id,
                    )
                    if not await request.is_disconnected():
                        yield json.dumps({"type": "interrupted", "session_id": resolved_session_id}, ensure_ascii=False) + "\n"
                    break
                if not is_stream_active(resolved_session_id, stream_generation):
                    end_reason = "superseded"
                    log_event(
                        "stream_superseded",
                        level="warning",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="failure",
                        error_type="stream_superseded",
                        session_id=resolved_session_id,
                    )
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
                if await request.is_disconnected():
                    disconnected = True
                    end_reason = "client_disconnected"
                    log_event(
                        "stream_client_disconnected",
                        level="warning",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="failure",
                        error_type="client_disconnected",
                        session_id=resolved_session_id,
                    )
                    break
                if is_interrupted(resolved_session_id):
                    end_reason = "interrupted"
                    log_event(
                        "stream_interrupted",
                        level="info",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="success",
                        session_id=resolved_session_id,
                    )
                    if not await request.is_disconnected():
                        yield json.dumps({"type": "interrupted", "session_id": resolved_session_id}, ensure_ascii=False) + "\n"
                    break
                if not is_stream_active(resolved_session_id, stream_generation):
                    end_reason = "superseded"
                    log_event(
                        "stream_superseded",
                        level="warning",
                        request_id=getattr(request.state, "request_id", ""),
                        endpoint=request.url.path,
                        status="failure",
                        error_type="stream_superseded",
                        session_id=resolved_session_id,
                    )
                    break
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
                if STREAM_CHUNK_DELAY_MS > 0:
                    await asyncio.sleep(STREAM_CHUNK_DELAY_MS / 1000.0)
                else:
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            disconnected = True
            end_reason = "cancelled"
            log_event(
                "stream_cancelled",
                level="warning",
                request_id=getattr(request.state, "request_id", ""),
                endpoint=request.url.path,
                status="failure",
                error_type="stream_cancelled",
                session_id=resolved_session_id,
            )
            return
        except Exception as exc:
            end_reason = "error"
            if intent_task and not intent_task.done():
                intent_task.cancel()
                try:
                    await intent_task
                except Exception:
                    pass

            log_event(
                "stream_processing_error",
                level="error",
                request_id=getattr(request.state, "request_id", ""),
                endpoint=request.url.path,
                status="failure",
                error_type=type(exc).__name__,
                session_id=resolved_session_id,
            )

            if not meta_sent:
                error_text = _lang_text(
                    request_language,
                    "We hit a streaming issue. Please try again.",
                    "à¤¸à¥à¤Ÿà¥à¤°à¥€à¤®à¤¿à¤‚à¤— à¤®à¥‡à¤‚ à¤¸à¤®à¤¸à¥à¤¯à¤¾ à¤¹à¥à¤ˆà¥¤ à¤•à¥ƒà¤ªà¤¯à¤¾ à¤«à¤¿à¤° à¤¸à¥‡ à¤•à¥‹à¤¶à¤¿à¤¶ à¤•à¤°à¥‡à¤‚à¥¤",
                )
                error_meta = {
                    **_base_response(
                        session_id=resolved_session_id,
                        response_text=error_text,
                        field_name=None,
                        validation_passed=False,
                        validation_error="stream_error",
                        session_complete=False,
                        mode="clarify",
                        action="retry",
                        quick_actions=[],
                        voice_text=error_text,
                    ),
                    "primary_intent": None,
                    "secondary_intents": [],
                }
                yield json.dumps({"type": "meta", "payload": error_meta}, ensure_ascii=False) + "\n"
        finally:
            if intent_task and not intent_task.done():
                intent_task.cancel()
                with contextlib.suppress(Exception):
                    await intent_task
            end_stream(resolved_session_id, stream_generation)
            if semaphore_acquired:
                request.app.state.concurrency_semaphore.release()
            log_event(
                "stream_end",
                request_id=getattr(request.state, "request_id", ""),
                endpoint=request.url.path,
                status="success" if end_reason == "completed" else "failure",
                error_type=None if end_reason == "completed" else end_reason,
                session_id=resolved_session_id,
                stream="process_text_stream",
                duration_ms=round((time.perf_counter() - stream_start) * 1000.0, 2),
            )

        if not disconnected:
            yield json.dumps({"type": "done", "session_id": resolved_session_id}, ensure_ascii=False) + "\n"

        response_time_ms = round((time.perf_counter() - route_start) * 1000.0, 2)
        log_event(
            "voice_process_text_stream_success",
            request_id=getattr(request.state, "request_id", ""),
            endpoint=request.url.path,
            method=request.method,
            status="success" if end_reason == "completed" else "failure",
            response_time_ms=response_time_ms,
            user_id=str(getattr(request.state, "user_id", "") or ""),
            error=None if end_reason == "completed" else end_reason,
        )

    return StreamingResponse(
        _iter_events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
    route_start = time.perf_counter()
    log_event(
        "voice_process_audio_start",
        request_id=getattr(request.state, "request_id", ""),
        endpoint=request.url.path,
        method=request.method,
        status="started",
        user_id=str(getattr(request.state, "user_id", "") or ""),
    )
    client_ip = request.client.host if request.client else "unknown"
    request_language = _resolve_request_language(language, x_language)
    timings = getattr(request.state, "timings", {})
    resolved_session_id = (session_id or user_id or "").strip() or str(uuid.uuid4())
    resolved_session_id = _validate_session_id(resolved_session_id, container.settings.max_session_id_chars)
    _enforce_session_rate_limit(resolved_session_id, user_id)
    try:
        get_session(resolved_session_id)
    except Exception:
        create_session(resolved_session_id)

    transcript = (text or "").strip()
    if is_interrupted(resolved_session_id):
        clear_interrupt(resolved_session_id)
    set_voice_state(resolved_session_id, "processing")
    try:
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
        intent_task = asyncio.create_task(container.intent_service.detect_async(transcript, debug=False, timings=timings))
        try:
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
            try:
                audio_base64 = await container.tts_service.synthesize_async(tts_text, request_language, timings=timings)
            except Exception as exc:
                audio_base64 = None
                log_event(
                    "tts_generation_failed",
                    level="warning",
                    request_id=getattr(request.state, "request_id", ""),
                    endpoint=request.url.path,
                    status="failure",
                    error_type=type(exc).__name__,
                    session_id=resolved_session_id,
                )

            try:
                _ = await intent_task
            except Exception as exc:
                log_event(
                    "intent_service_async_failure",
                    level="warning",
                    request_id=getattr(request.state, "request_id", ""),
                    endpoint=request.url.path,
                    status="failure",
                    error_type=type(exc).__name__,
                    session_id=resolved_session_id,
                )
            request.state.intent = conversation_result.get("primary_intent")
            request.state.confidence = (conversation_result.get("intent_debug") or {}).get("confidence")
            record_latency_perception(resolved_session_id, (time.perf_counter() - start) * 1000.0)
            if not conversation_result.get("validation_passed", True):
                record_retry(resolved_session_id)
        except Exception:
            if not intent_task.done():
                intent_task.cancel()
                try:
                    await intent_task
                except Exception:
                    pass
            raise
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
        "tts_error": None if audio_base64 else "tts_failed",
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

    response_time_ms = round((time.perf_counter() - route_start) * 1000.0, 2)
    log_event(
        "voice_process_audio_success",
        request_id=getattr(request.state, "request_id", ""),
        endpoint=request.url.path,
        method=request.method,
        status="success",
        response_time_ms=response_time_ms,
        user_id=str(getattr(request.state, "user_id", "") or ""),
    )
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
        async with get_async_session_lock(resolved_session_id):
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

        async with get_async_session_lock(resolved_session_id):
            session = get_session(resolved_session_id)
            session["language"] = request_language
            session = container.conversation_service.merge_ocr(session, ocr_data)

        extracted_fields = session.get("ocr_extracted", {}).get("fields", [])
        if not extracted_fields:
            async with get_async_session_lock(resolved_session_id):
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
        async with get_async_session_lock(resolved_session_id):
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
async def trigger_autofill(payload: AutofillRequest):
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
    script_path = Path(__file__).resolve().parents[1] / "automation" / "autofill_service.js"
    success = False
    fallback_used = False
    started = time.perf_counter()
    try:
        await asyncio.to_thread(payload_path.write_text, json.dumps(session), "utf-8")
        process = await asyncio.create_subprocess_exec(
            "node",
            str(script_path),
            str(payload_path),
            cwd=str(Path(__file__).resolve().parents[2]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            stdout, stderr = b"", b""

        output = f"{stdout.decode(errors='replace')}\n{stderr.decode(errors='replace')}".strip()
        fallback_used = "label-" in output or "failed fields" in output.lower()
        success = process.returncode == 0 and "AUTOFILL_RESULT:done" in output
    except Exception:
        success = False
        fallback_used = False
    finally:
        with contextlib.suppress(OSError):
            payload_path.unlink(missing_ok=True)

    record_timing("automation_autofill_ms", (time.perf_counter() - started) * 1000.0)
    record_automation_result(success=success, fallback_used=fallback_used)

    if not success:
        return standardized_success({
            **_base_response(
                session_id=session_id,
                response_text="autofill_failed",
                validation_passed=False,
                validation_error="autofill_failed",
                session_complete=True,
            ),
            "status": "autofill_failed",
        })

    return standardized_success({
        **_base_response(session_id=session_id, response_text="autofill_completed", validation_passed=True, validation_error=None, session_complete=True),
        "status": "autofill_completed",
    })


@router.post("/reset-session")
def reset_session(payload: ResetSessionRequest):
    session_id = (payload.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    delete_session(session_id)
    create_session(session_id)
    return standardized_success({"status": "reset", "session_id": session_id})
