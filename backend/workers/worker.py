"""
backend/workers/worker.py

Production-grade background ML worker.

Run as a separate process:
    python -m backend.workers.worker

Features:
  - Loads ML models ONCE at startup (never in the API process)
  - Status transitions: pending → processing → done | failed
  - Retry up to MAX_RETRIES times with linear backoff
  - Dead Letter Queue for permanently failed jobs
  - Per-stage structured logging {job_id, session_id, stage, duration_ms}
  - asyncio.wait_for timeout on each job (WORKER_JOB_TIMEOUT_SECONDS)
  - Multi-worker safe: BRPOP is atomic — each job consumed by exactly one worker
  - Graceful SIGINT / SIGTERM shutdown
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
import uuid
from typing import Any, Dict, Optional

# ── Logging ──────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WORKER] %(levelname)s %(message)s",
)
logger = logging.getLogger("voice_os.worker")

# ── Config ────────────────────────────────────────────────────────────────────────
MAX_RETRIES              = int(os.getenv("WORKER_MAX_RETRIES", "3"))
JOB_TIMEOUT_SECONDS      = float(os.getenv("WORKER_JOB_TIMEOUT_SECONDS", "120"))
RETRY_BACKOFF_SECONDS    = float(os.getenv("WORKER_RETRY_BACKOFF_SECONDS", "2"))   # linear: attempt * backoff
HEARTBEAT_INTERVAL       = float(os.getenv("WORKER_HEARTBEAT_INTERVAL_SECONDS", "30"))

# Unique ID for this worker process — used for heartbeat and logs
WORKER_ID = str(uuid.uuid4())[:8]

# ── Lazy model singletons — loaded ONCE when worker boots ─────────────────────────
_stt_service: Any          = None
_tts_service: Any          = None
_conversation_service: Any = None
_intent_service: Any       = None


def _load_models() -> None:
    global _stt_service, _tts_service, _conversation_service, _intent_service
    logger.info("Loading ML models …")

    try:
        from backend.services.stt_service import SttService
        _stt_service = SttService()
        logger.info("STT service ready")
    except Exception as exc:
        logger.warning("STT service failed to load: %s", exc)

    try:
        from backend.services.tts_service import TtsService
        _tts_service = TtsService()
        logger.info("TTS service ready")
    except Exception as exc:
        logger.warning("TTS service failed to load: %s", exc)

    try:
        from backend.services.conversation_service import ConversationService
        from backend.services.intent_service import IntentService
        _intent_service = IntentService()
        _conversation_service = ConversationService()
        logger.info("Conversation + Intent services ready")
    except Exception as exc:
        logger.warning("Conversation/Intent services failed to load: %s", exc)


# ── Structured stage logger ───────────────────────────────────────────────────────
def _log_stage(
    job_id: str,
    session_id: str,
    stage: str,
    duration_ms: float,
    status: str = "ok",
    detail: Optional[str] = None,
) -> None:
    """Emit a structured log line per stage and record to shared Redis metrics."""
    record: Dict[str, Any] = {
        "job_id":      job_id,
        "session_id":  session_id,
        "stage":       stage,
        "duration_ms": int(duration_ms * 100) / 100,
        "status":      status,
        "worker_id":   WORKER_ID,
    }
    if detail:
        record["detail"] = detail
    if status == "ok":
        logger.info("STAGE %s", record)
    else:
        logger.error("STAGE %s", record)

    # Cross-process metrics (Redis-backed, fails silently when unavailable)
    try:
        from backend.infrastructure.monitoring.metrics import record_latency
        record_latency(stage, duration_ms)
    except Exception:
        pass


# ── Pipeline ──────────────────────────────────────────────────────────────────────
async def _process_pipeline(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the full STT → Intent → RAG → TTS pipeline for a single job.
    Returns a result dict (always — errors are represented as status=error).
    """
    job_id     = job["job_id"]
    session_id = job["session_id"]
    payload    = job.get("payload", {})

    logger.info(
        "Processing job %s (type=%s session=%s retry=%s)",
        job_id, job.get("type", "pipeline"), session_id, job.get("retry_count", 0),
    )

    result: Dict[str, Any] = {
        "job_id":     job_id,
        "session_id": session_id,
        "status":     "ok",
    }

    # ── STT ─────────────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    transcript = payload.get("transcript") or ""
    if not transcript and payload.get("audio_bytes") and _stt_service:
        import os as _os
        import tempfile
        audio_bytes = bytes(payload["audio_bytes"])
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            transcript = _stt_service.transcribe(tmp_path, language=payload.get("language", "en"))
        finally:
            _os.unlink(tmp_path)
    _log_stage(job_id, session_id, "stt", (time.perf_counter() - t0) * 1000)
    result["transcript"] = transcript

    # ── Intent + RAG (Conversation) ──────────────────────────────────────────────
    t0 = time.perf_counter()
    if transcript and _conversation_service:
        conversation_result = await asyncio.to_thread(
            _conversation_service.process,
            session_id,
            transcript,
            payload.get("language", "en"),
            False,
        )
        result["conversation"] = conversation_result
        response_text = (
            conversation_result.get("voice_text")
            or conversation_result.get("response_text", "")
        )
    else:
        response_text = ""
        result["conversation"] = {}
    _log_stage(job_id, session_id, "intent+rag", (time.perf_counter() - t0) * 1000)
    result["response_text"] = response_text

    # ── TTS ──────────────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    if response_text and _tts_service:
        audio_b64 = await _tts_service.synthesize_async(
            response_text, payload.get("language", "en")
        )
        result["audio_base64"] = audio_b64
    else:
        result["audio_base64"] = None
    _log_stage(job_id, session_id, "tts", (time.perf_counter() - t0) * 1000)

    return result


async def _run_with_timeout(job: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap _process_pipeline in a timeout guard."""
    try:
        return await asyncio.wait_for(
            _process_pipeline(job), timeout=JOB_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"Job timed out after {JOB_TIMEOUT_SECONDS}s"
        )


# ── Main worker loop ──────────────────────────────────────────────────────────────
_RUNNING = True


def _handle_shutdown(signum: int, frame: Any) -> None:
    global _RUNNING
    logger.info("Shutdown signal received (%s), draining current job then stopping …", signum)
    _RUNNING = False


async def run_worker() -> None:
    from backend.infrastructure.queue.redis_queue import (
        MAX_RETRIES,
        clear_job_processing,
        dequeue_job,
        mark_job_processing,
        push_dead_letter,
        requeue_job,
        set_job_status,
        store_result,
        write_worker_heartbeat,
    )
    from backend.infrastructure.pubsub.redis_pubsub import publish_result
    from backend.infrastructure.monitoring.metrics import increment

    logger.info(
        "Worker %s started — MAX_RETRIES=%s JOB_TIMEOUT=%ss HEARTBEAT=%ss",
        WORKER_ID, MAX_RETRIES, JOB_TIMEOUT_SECONDS, HEARTBEAT_INTERVAL,
    )

    # Heartbeat background coroutine
    async def _heartbeat_loop() -> None:
        while _RUNNING:
            write_worker_heartbeat(WORKER_ID)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    asyncio.ensure_future(_heartbeat_loop())
    write_worker_heartbeat(WORKER_ID)   # immediate first heartbeat

    while _RUNNING:
        job = await asyncio.to_thread(dequeue_job, 1.0)
        if job is None:
            continue

        assert job is not None  # narrow Optional for type checker
        job_id     = job["job_id"]
        session_id = job["session_id"]
        retry      = job.get("retry_count", 0)

        # Register in ZSET so sweeper can detect crashes
        set_job_status(job_id, "processing")
        mark_job_processing(job_id, job)
        job_start = time.perf_counter()

        try:
            result = await _run_with_timeout(job)
            result["status"] = "ok"

            # Persist result then notify WebSocket
            store_result(job_id, result)
            set_job_status(job_id, "done")
            clear_job_processing(job_id)
            await publish_result(job_id, result)

            increment("jobs_processed_total")
            elapsed_ms = int((time.perf_counter() - job_start) * 100_000) / 100
            logger.info(
                "Worker %s | Job %s DONE in %.0fms (session=%s)",
                WORKER_ID, job_id, elapsed_ms, session_id,
            )

        except Exception as exc:
            clear_job_processing(job_id)   # always remove from ZSET
            elapsed_ms = int((time.perf_counter() - job_start) * 100_000) / 100
            logger.error(
                "Worker %s | Job %s FAILED in %.0fms (retry=%s/%s): %s",
                WORKER_ID, job_id, elapsed_ms, retry, MAX_RETRIES, exc, exc_info=True,
            )

            if retry < MAX_RETRIES:
                backoff = (retry + 1) * RETRY_BACKOFF_SECONDS
                logger.info(
                    "Retrying job %s in %.1fs (attempt %s/%s) …",
                    job_id, backoff, retry + 1, MAX_RETRIES,
                )
                await asyncio.sleep(backoff)
                requeue_job(job)
            else:
                # Permanently failed → Dead Letter Queue
                set_job_status(job_id, "failed")
                push_dead_letter(job, str(exc))
                increment("jobs_failed_total")

                error_result = {
                    "job_id":     job_id,
                    "session_id": session_id,
                    "status":     "error",
                    "error":      str(exc),
                }
                store_result(job_id, error_result)
                await publish_result(job_id, error_result)


def main() -> None:
    signal.signal(signal.SIGINT,  _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)
    _load_models()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
