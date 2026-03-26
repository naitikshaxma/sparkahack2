import os
import time
from typing import AsyncIterator, Callable

import asyncio

from ..logger import log_event
from ..metrics import record_timing
from ..tts_service import generate_tts, generate_tts_bytes, split_tts_chunks

DEFAULT_TTS_RETRY_ATTEMPTS = max(1, int((os.getenv("TTS_RETRY_ATTEMPTS") or "2").strip() or "2"))
DEFAULT_TTS_RETRY_BACKOFF_MS = max(0, int((os.getenv("TTS_RETRY_BACKOFF_MS") or "250").strip() or "250"))


def _retry_call(func, *args, attempts: int, backoff_ms: int):
    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return func(*args)
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            time.sleep((backoff_ms / 1000.0) * attempt)
    if last_exc:
        raise last_exc
    raise RuntimeError("TTS retry failed without exception")


class TTSService:
    def synthesize(self, text: str, language: str, timings: dict | None = None) -> str:
        start = time.perf_counter()
        log_event("tts_service_start", endpoint="tts_service", status="success", user_input_length=len(text or ""))
        try:
            audio = _retry_call(generate_tts, text, language, attempts=DEFAULT_TTS_RETRY_ATTEMPTS, backoff_ms=DEFAULT_TTS_RETRY_BACKOFF_MS)
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["tts_ms"] = elapsed_ms
            record_timing("tts_sync_ms", elapsed_ms)
            log_event("tts_service_success", endpoint="tts_service", status="success", response_time_ms=elapsed_ms)
            return audio
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["tts_ms"] = elapsed_ms
            record_timing("tts_sync_ms", elapsed_ms)
            log_event(
                "tts_service_failure",
                level="error",
                endpoint="tts_service",
                status="failure",
                error_type=type(exc).__name__,
                response_time_ms=elapsed_ms,
            )
            raise

    async def synthesize_async(self, text: str, language: str, timings: dict | None = None) -> str:
        start = time.perf_counter()
        log_event("tts_service_async_start", endpoint="tts_service", status="success", user_input_length=len(text or ""))
        try:
            audio = await asyncio.to_thread(
                _retry_call,
                generate_tts,
                text,
                language,
                attempts=DEFAULT_TTS_RETRY_ATTEMPTS,
                backoff_ms=DEFAULT_TTS_RETRY_BACKOFF_MS,
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["tts_ms"] = elapsed_ms
            record_timing("tts_async_ms", elapsed_ms)
            log_event("tts_service_async_success", endpoint="tts_service", status="success", response_time_ms=elapsed_ms)
            return audio
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["tts_ms"] = elapsed_ms
            record_timing("tts_async_ms", elapsed_ms)
            log_event("tts_service_async_failure", level="error", endpoint="tts_service", status="failure", error_type=type(exc).__name__, response_time_ms=elapsed_ms)
            raise

    async def stream_synthesize_async(self, text: str, language: str, *, interrupted: Callable[[], bool] | None = None, timings: dict | None = None) -> AsyncIterator[bytes]:
        overall_start = time.perf_counter()
        chunks = split_tts_chunks(text)
        for index, chunk in enumerate(chunks):
            if interrupted and interrupted():
                break
            try:
                data = await asyncio.to_thread(
                    _retry_call,
                    generate_tts_bytes,
                    chunk,
                    language,
                    attempts=DEFAULT_TTS_RETRY_ATTEMPTS,
                    backoff_ms=DEFAULT_TTS_RETRY_BACKOFF_MS,
                )
            except Exception as exc:
                log_event(
                    "tts_stream_chunk_failure",
                    level="warning",
                    endpoint="tts_service",
                    status="failure",
                    error_type=type(exc).__name__,
                    chunk_index=index,
                )
                continue
            if interrupted and interrupted():
                break
            if data:
                yield data
        if timings is not None:
            timings["tts_stream_ms"] = round((time.perf_counter() - overall_start) * 1000.0, 2)
        record_timing("tts_stream_ms", (time.perf_counter() - overall_start) * 1000.0)
