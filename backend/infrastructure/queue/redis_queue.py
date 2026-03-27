"""
backend/infrastructure/queue/redis_queue.py

Production-grade Redis job queue with:
  - Job status tracking  (voice_os:job_status:{job_id})
  - Result storage       (voice_os:result_data:{job_id})
  - Dead Letter Queue    (voice_os:dead_letter)
  - Retry counter        (job["retry_count"])
  - In-memory fallback for every operation
"""
from __future__ import annotations

import json
import logging
import os
import queue
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    import redis  # type: ignore
except ImportError:
    redis = None  # type: ignore

logger = logging.getLogger("voice_os.queue")

# ── Redis key schema ────────────────────────────────────────────────────────────
QUEUE_KEY          = "voice_os:job_queue"
STATUS_KEY         = "voice_os:job_status:{job_id}"   # STRING  pending|processing|done|failed
RESULT_KEY         = "voice_os:result_data:{job_id}"  # STRING  JSON result blob
DEAD_LETTER_KEY    = "voice_os:dead_letter"            # LIST    failed job entries
PROCESSING_SET_KEY = "voice_os:processing_jobs"       # ZSET    score=started_at, member=job_id
JOB_DATA_KEY       = "voice_os:job_data:{job_id}"     # STRING  full job JSON (for sweeper)
RATELIMIT_KEY      = "voice_os:ratelimit:{session_id}" # ZSET   sliding-window timestamps
HEARTBEAT_KEY      = "voice_os:worker:{worker_id}:heartbeat"  # STRING  TTL-based liveness

RESULT_TTL_SECONDS    = 600    # 10 min — enough time for client reconnect
STATUS_TTL_SECONDS    = 600
JOB_DATA_TTL_SECONDS  = 1800   # 30 min — covers sweeper window comfortably
HEARTBEAT_TTL_SECONDS = 60    # worker must refresh every <60s to stay "live"

MAX_RETRIES = int(os.getenv("WORKER_MAX_RETRIES", "3"))
BACKPRESSURE_THRESHOLD = int(os.getenv("BACKPRESSURE_QUEUE_THRESHOLD", "200"))  # reject if queue > this

# ── In-memory fallbacks (single-process dev mode) ───────────────────────────────
_FALLBACK_QUEUE: queue.SimpleQueue = queue.SimpleQueue()
_MEM_STATUS:   Dict[str, str]            = {}
_MEM_RESULTS:  Dict[str, Dict[str, Any]] = {}
_MEM_PROC_SET: Dict[str, float]          = {}   # job_id → started_at
_MEM_JOB_DATA: Dict[str, Dict[str, Any]] = {}

_redis_client: Optional[Any] = None


# ── Redis connection ─────────────────────────────────────────────────────────────
def _get_redis() -> Optional[Any]:
    global _redis_client
    if redis is None:
        return None
    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None
    try:
        from backend.core.config import get_settings
        settings = get_settings()
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None


# ── Job factory ──────────────────────────────────────────────────────────────────
def make_job(
    *,
    session_id: str,
    job_type: str,
    payload: Dict[str, Any],
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a canonical job dict."""
    return {
        "job_id": job_id or str(uuid.uuid4()),
        "session_id": session_id,
        "type": job_type,
        "payload": payload,
        "retry_count": 0,
        "enqueued_at": time.time(),
    }


# ── Enqueue / Dequeue ─────────────────────────────────────────────────────────────
def enqueue_job(job: Dict[str, Any]) -> bool:
    """
    Push job to Redis LPUSH and mark status = pending.
    Returns True if enqueued to Redis, False if fell back to memory.
    """
    set_job_status(job["job_id"], "pending")
    r = _get_redis()
    if r is not None:
        try:
            r.lpush(QUEUE_KEY, json.dumps(job))
            logger.debug("Enqueued job %s (retry=%s)", job["job_id"], job.get("retry_count", 0))
            return True
        except Exception as exc:
            logger.warning("Redis enqueue failed, falling back to memory: %s", exc)
    _FALLBACK_QUEUE.put(job)
    return False


def dequeue_job(timeout_seconds: float = 1.0) -> Optional[Dict[str, Any]]:
    """
    Pop one job (Redis BRPOP with timeout, or in-memory queue).
    Returns None on timeout or empty queue.
    """
    r = _get_redis()
    if r is not None:
        try:
            result = r.brpop(QUEUE_KEY, timeout=int(timeout_seconds))
            if result:
                _, raw = result
                return json.loads(raw)
            return None
        except Exception as exc:
            logger.warning("Redis dequeue failed, falling back to memory: %s", exc)
    try:
        return _FALLBACK_QUEUE.get(timeout=timeout_seconds)
    except queue.Empty:
        return None


def requeue_job(job: Dict[str, Any]) -> bool:
    """Re-enqueue a job for retry, incrementing its retry_count."""
    retried = dict(job)
    retried["retry_count"] = retried.get("retry_count", 0) + 1
    return enqueue_job(retried)


# ── Status tracking ───────────────────────────────────────────────────────────────
def set_job_status(job_id: str, status: str) -> None:
    """
    Set job lifecycle status. Valid values: pending | processing | done | failed.
    Stored with TTL so Redis doesn't accumulate stale keys.
    """
    r = _get_redis()
    if r is not None:
        try:
            r.setex(STATUS_KEY.format(job_id=job_id), STATUS_TTL_SECONDS, status)
            return
        except Exception:
            pass
    _MEM_STATUS[job_id] = status


def get_job_status(job_id: str) -> Optional[str]:
    """Return current job status, or None if unknown."""
    r = _get_redis()
    if r is not None:
        try:
            return r.get(STATUS_KEY.format(job_id=job_id))
        except Exception:
            pass
    return _MEM_STATUS.get(job_id)


# ── Result storage ────────────────────────────────────────────────────────────────
def store_result(job_id: str, result: Dict[str, Any]) -> None:
    """
    Persist the full result payload so a reconnecting client can fetch it.
    TTL = RESULT_TTL_SECONDS (default 10 min).
    """
    r = _get_redis()
    if r is not None:
        try:
            r.setex(
                RESULT_KEY.format(job_id=job_id),
                RESULT_TTL_SECONDS,
                json.dumps(result),
            )
            return
        except Exception:
            pass
    _MEM_RESULTS[job_id] = result


def get_result(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a stored result by job_id.
    Returns None if the result has expired or never existed.
    """
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(RESULT_KEY.format(job_id=job_id))
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return _MEM_RESULTS.get(job_id)


# ── Dead Letter Queue ──────────────────────────────────────────────────────────────
def push_dead_letter(job: Dict[str, Any], error: str) -> None:
    """
    Push a permanently-failed job to the dead letter queue.
    Includes job_id, payload, retry_count, error message, and timestamp.
    """
    entry = {
        "job_id":      job.get("job_id"),
        "session_id":  job.get("session_id"),
        "payload":     job.get("payload", {}),
        "retry_count": job.get("retry_count", 0),
        "error":       error,
        "failed_at":   time.time(),
    }
    r = _get_redis()
    if r is not None:
        try:
            r.lpush(DEAD_LETTER_KEY, json.dumps(entry))
            logger.error(
                "Job %s sent to DLQ after %s retries. Error: %s",
                entry["job_id"], entry["retry_count"], error,
            )
            return
        except Exception:
            pass
    # No Redis: log so it's not silently lost
    logger.error("DLQ (no Redis) — job %s failed permanently: %s", entry["job_id"], error)


def get_dead_letters(count: int = 10) -> List[Dict[str, Any]]:
    """Read up to `count` entries from the dead letter queue (non-destructive LRANGE)."""
    r = _get_redis()
    if r is not None:
        try:
            items = r.lrange(DEAD_LETTER_KEY, 0, count - 1)
            return [json.loads(i) for i in items]
        except Exception:
            pass
    return []


# ── Diagnostics ───────────────────────────────────────────────────────────────────
def queue_length() -> int:
    """How many jobs are pending in the main queue."""
    r = _get_redis()
    if r is not None:
        try:
            return int(r.llen(QUEUE_KEY))
        except Exception:
            pass
    return _FALLBACK_QUEUE.qsize()


def dead_letter_length() -> int:
    """How many jobs are in the dead letter queue."""
    r = _get_redis()
    if r is not None:
        try:
            return int(r.llen(DEAD_LETTER_KEY))
        except Exception:
            pass
    return 0


# ── Processing-set tracking (used by sweeper) ──────────────────────────────────────
def mark_job_processing(job_id: str, job: Dict[str, Any]) -> None:
    """
    Called by the worker as it begins a job.
    - Adds job_id to the processing sorted set (score = current timestamp)
    - Stores full job JSON so the sweeper can re-queue it if stuck
    """
    now = time.time()
    r = _get_redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.zadd(PROCESSING_SET_KEY, {job_id: now})
            pipe.setex(JOB_DATA_KEY.format(job_id=job_id), JOB_DATA_TTL_SECONDS, json.dumps(job))
            pipe.execute()
            return
        except Exception:
            pass
    _MEM_PROC_SET[job_id] = now
    _MEM_JOB_DATA[job_id] = job


def clear_job_processing(job_id: str) -> None:
    """
    Called by the worker when a job completes (success OR failure).
    Removes job_id from the processing sorted set.
    """
    r = _get_redis()
    if r is not None:
        try:
            r.zrem(PROCESSING_SET_KEY, job_id)
            return
        except Exception:
            pass
    _MEM_PROC_SET.pop(job_id, None)


def get_stuck_jobs(threshold_seconds: float) -> List[Dict[str, Any]]:
    """
    Return all jobs that have been in 'processing' state for > threshold_seconds.
    Used by the sweeper to detect crashed workers.
    """
    cutoff = time.time() - threshold_seconds
    stuck: List[Dict[str, Any]] = []

    r = _get_redis()
    if r is not None:
        try:
            job_ids = r.zrangebyscore(PROCESSING_SET_KEY, 0, cutoff)
            for jid in job_ids:
                raw = r.get(JOB_DATA_KEY.format(job_id=jid))
                if raw:
                    try:
                        stuck.append(json.loads(raw))
                    except Exception:
                        pass
                # Remove from set regardless — we'll handle it now
                r.zrem(PROCESSING_SET_KEY, jid)
            return stuck
        except Exception:
            pass

    # In-memory fallback
    now = time.time()
    for jid, started_at in list(_MEM_PROC_SET.items()):
        if now - started_at > threshold_seconds:
            job_data = _MEM_JOB_DATA.pop(jid, {"job_id": jid})
            _MEM_PROC_SET.pop(jid, None)
            stuck.append(job_data)
    return stuck


# ── Backpressure ───────────────────────────────────────────────────────────────────
def check_backpressure() -> bool:
    """
    Returns True if the queue is under the backpressure threshold (safe to enqueue).
    Returns False if the queue is full — caller should reject the request.
    """
    return queue_length() < BACKPRESSURE_THRESHOLD


# ── Per-session rate limiting (sliding window) ────────────────────────────────────
def check_session_rate_limit(
    session_id: str,
    max_requests: int = 10,
    window_seconds: int = 60,
) -> bool:
    """
    Sliding-window rate limiter using a Redis sorted set.
    Returns True if the request is allowed, False if the session is over the limit.
    Gracefully allows all requests when Redis is unavailable.
    """
    r = _get_redis()
    if r is None:
        return True   # no Redis → allow (dev mode)

    key = RATELIMIT_KEY.format(session_id=session_id)
    now = time.time()
    window_start = now - window_seconds

    try:
        pipe = r.pipeline()
        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)
        # Count remaining (within window)
        pipe.zcard(key)
        # Add current request timestamp
        pipe.zadd(key, {str(now): now})
        # Expire the key after the window (TTL cleanup)
        pipe.expire(key, window_seconds + 5)
        results = pipe.execute()
        current_count = results[1]   # count BEFORE adding this request
        return int(current_count) < max_requests
    except Exception:
        return True   # Redis error → allow (fail open)


# ── Worker heartbeat ───────────────────────────────────────────────────────────────
def write_worker_heartbeat(worker_id: str) -> None:
    """
    Write a heartbeat key for this worker instance with TTL.
    The /ready endpoint counts live workers by scanning these keys.
    Key expires automatically if worker crashes without calling this.
    """
    r = _get_redis()
    if r is not None:
        try:
            r.setex(
                HEARTBEAT_KEY.format(worker_id=worker_id),
                HEARTBEAT_TTL_SECONDS,
                str(time.time()),
            )
        except Exception:
            pass

