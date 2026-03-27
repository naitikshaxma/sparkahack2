"""
backend/infrastructure/pubsub/redis_pubsub.py

Redis Pub/Sub for broadcasting ML worker results back to API WebSocket handlers.
Falls back to in-memory asyncio.Queue when Redis is unavailable.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, Optional

try:
    import redis.asyncio as aioredis  # type: ignore
except ImportError:
    aioredis = None  # type: ignore

CHANNEL_PREFIX = "voice_os:result:"
_MEMORY_CHANNELS: Dict[str, asyncio.Queue] = {}
_async_redis_client: Optional[Any] = None


def _channel(job_id: str) -> str:
    return f"{CHANNEL_PREFIX}{job_id}"


async def _get_async_redis() -> Optional[Any]:
    global _async_redis_client
    if aioredis is None:
        return None
    if _async_redis_client is not None:
        try:
            await _async_redis_client.ping()
            return _async_redis_client
        except Exception:
            _async_redis_client = None
    try:
        from backend.core.config import get_settings
        settings = get_settings()
        _async_redis_client = await aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=2,
        )
        await _async_redis_client.ping()
        return _async_redis_client
    except Exception:
        return None


async def publish_result(job_id: str, data: Dict[str, Any]) -> bool:
    """
    Publish a completed job result to the job's channel.
    Returns True if published to Redis, False if fell back to memory.
    """
    r = await _get_async_redis()
    if r is not None:
        try:
            await r.publish(_channel(job_id), json.dumps(data))
            return True
        except Exception:
            pass
    # Fallback: put into in-memory asyncio queue
    q = _MEMORY_CHANNELS.get(job_id)
    if q is not None:
        await q.put(data)
    return False


async def subscribe_result(
    job_id: str,
    timeout_seconds: float = 60.0,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Async generator that yields result payloads for a given job_id.
    Automatically unsubscribes / cleans up after first result or timeout.
    """
    r = await _get_async_redis()
    if r is not None:
        try:
            pubsub = r.pubsub()
            await pubsub.subscribe(_channel(job_id))
            deadline = asyncio.get_event_loop().time() + timeout_seconds
            async for message in pubsub.listen():
                if asyncio.get_event_loop().time() > deadline:
                    break
                if message.get("type") == "message" and message.get("data"):
                    yield json.loads(message["data"])
                    break
            await pubsub.unsubscribe(_channel(job_id))
            await pubsub.aclose()
            return
        except Exception:
            pass
    # Fallback: in-memory queue
    if job_id not in _MEMORY_CHANNELS:
        _MEMORY_CHANNELS[job_id] = asyncio.Queue()
    q = _MEMORY_CHANNELS[job_id]
    try:
        result = await asyncio.wait_for(q.get(), timeout=timeout_seconds)
        yield result
    except asyncio.TimeoutError:
        pass
    finally:
        _MEMORY_CHANNELS.pop(job_id, None)
