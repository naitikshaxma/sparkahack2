"""
backend/api/v1/routes/voice_ws.py

WebSocket endpoint for the async voice pipeline.

Flow:
  1. Client connects and sends JSON payload
  2. API enqueues a job → Redis job queue
  3. Worker processes: STT → Intent → RAG → TTS
  4. Worker stores result → Redis (voice_os:result_data:{job_id})
  5. Worker publishes → Redis Pub/Sub (voice_os:result:{job_id})
  6. API WebSocket subscribes and streams result to client

Reconnect / result-fetch:
  - Client sends {"fetch_result": true, "job_id": "..."} to retrieve a stored result
    even if the WebSocket dropped and reconnected.

Fallback:
  - If Redis is unavailable, runs full pipeline synchronously in the API process.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.logger import log_event
from backend.infrastructure.queue.redis_queue import (
    enqueue_job,
    get_job_status,
    get_result,
    make_job,
)
from backend.infrastructure.pubsub.redis_pubsub import subscribe_result

router = APIRouter(tags=["voice-ws"])

# How long the WebSocket waits for the worker to publish a result
JOB_TIMEOUT_SECONDS = float(90)


# ── Sync fallback (no Redis / local dev) ─────────────────────────────────────────
async def _process_sync_fallback(
    session_id: str,
    transcript: str,
    language: str,
) -> dict:
    """Run the full pipeline inline when Redis is unavailable."""
    import asyncio
    try:
        from backend.services.conversation_service import ConversationService
        from backend.services.tts_service import TtsService

        conv_service = ConversationService()
        tts_service  = TtsService()

        conversation_result = await asyncio.to_thread(
            conv_service.process, session_id, transcript, language, False
        )
        response_text = (
            conversation_result.get("voice_text")
            or conversation_result.get("response_text", "")
        )
        audio_b64: Optional[str] = None
        try:
            audio_b64 = await tts_service.synthesize_async(response_text, language)
        except Exception:
            pass

        return {
            "status":        "ok",
            "job_id":        str(uuid.uuid4()),
            "session_id":    session_id,
            "transcript":    transcript,
            "response_text": response_text,
            "audio_base64":  audio_b64,
            "conversation":  conversation_result,
            "fallback_mode": True,
        }
    except Exception as exc:
        return {
            "status":        "error",
            "error":         str(exc),
            "session_id":    session_id,
            "fallback_mode": True,
        }


# ── WebSocket endpoint ────────────────────────────────────────────────────────────
@router.websocket("/ws/voice/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket voice pipeline endpoint.

    Client sends JSON:
        {"text": "...", "language": "hi"}        — process new query
        {"cancel": true}                          — cancel / no-op
        {"fetch_result": true, "job_id": "..."}   — retrieve stored result after reconnect

    Server sends JSON events:
        {"type": "ack",    "job_id": "..."}
        {"type": "status", "job_id": "...", "status": "processing"}
        {"type": "result", "payload": {...}}
        {"type": "error",  "error":  "...", "job_id": "..."}
        {"type": "done",   "job_id": "..."}
        {"type": "cancelled"}
    """
    await websocket.accept()
    log_event("ws_voice_connect", session_id=session_id, status="success")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "invalid_json"})
                continue

            # ── Cancellation ─────────────────────────────────────────────────────
            if msg.get("cancel"):
                await websocket.send_json({"type": "cancelled"})
                continue

            # ── Reconnect: fetch stored result by job_id ──────────────────────────
            if msg.get("fetch_result"):
                job_id = (msg.get("job_id") or "").strip()
                if not job_id:
                    await websocket.send_json({"type": "error", "error": "missing job_id"})
                    continue

                # Check status first
                status = get_job_status(job_id)
                if status in ("pending", "processing"):
                    await websocket.send_json({"type": "status", "job_id": job_id, "status": status})
                    continue

                stored = get_result(job_id)
                if stored:
                    await websocket.send_json({"type": "result", "payload": stored})
                    await websocket.send_json({"type": "done", "job_id": job_id})
                else:
                    await websocket.send_json({
                        "type":    "error",
                        "error":   "result_not_found",
                        "job_id":  job_id,
                        "message": "Result expired or job_id unknown.",
                    })
                continue

            # ── New query ─────────────────────────────────────────────────────────
            transcript = (msg.get("text") or "").strip()
            language   = (msg.get("language") or "en").strip()

            if not transcript:
                await websocket.send_json({"type": "error", "error": "empty_text"})
                continue

            job    = make_job(
                session_id=session_id,
                job_type="pipeline",
                payload={"transcript": transcript, "language": language},
            )
            job_id = job["job_id"]

            # Enqueue (returns False = Redis unavailable → use sync fallback)
            redis_available = enqueue_job(job)
            await websocket.send_json({"type": "ack", "job_id": job_id})

            # ── Sync fallback ─────────────────────────────────────────────────────
            if not redis_available:
                log_event("ws_sync_fallback", session_id=session_id, job_id=job_id)
                result = await _process_sync_fallback(session_id, transcript, language)
                await websocket.send_json({"type": "result", "payload": result})
                await websocket.send_json({"type": "done", "job_id": job_id})
                continue

            # ── Async path: subscribe to Pub/Sub, stream result ───────────────────
            got_result = False
            async for result in subscribe_result(job_id, timeout_seconds=JOB_TIMEOUT_SECONDS):
                await websocket.send_json({"type": "result", "payload": result})
                got_result = True
                break

            if not got_result:
                # Pub/Sub timed out — check if result was stored anyway
                # (handles the case where worker finished but pub/sub message was lost)
                stored = get_result(job_id)
                if stored:
                    log_event(
                        "ws_result_recovered_from_storage",
                        session_id=session_id,
                        job_id=job_id,
                    )
                    await websocket.send_json({"type": "result", "payload": stored})
                else:
                    await websocket.send_json({
                        "type":    "error",
                        "error":   "timeout",
                        "job_id":  job_id,
                        "message": "Worker did not respond in time. Use fetch_result to retry.",
                    })

            await websocket.send_json({"type": "done", "job_id": job_id})

    except WebSocketDisconnect:
        log_event("ws_voice_disconnect", session_id=session_id, status="success")
    except Exception as exc:
        log_event(
            "ws_voice_error",
            session_id=session_id,
            status="failure",
            error_type=type(exc).__name__,
        )
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except Exception:
            pass
