import time
from typing import AsyncIterator, Callable

import asyncio

from ..logger import log_event
from ..tts_service import generate_tts, generate_tts_bytes, split_tts_chunks


class TTSService:
    def synthesize(self, text: str, language: str, timings: dict | None = None) -> str:
        start = time.perf_counter()
        log_event("tts_service_start", endpoint="tts_service", status="success", user_input_length=len(text or ""))
        try:
            audio = generate_tts(text, language)
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["tts_ms"] = elapsed_ms
            log_event("tts_service_success", endpoint="tts_service", status="success", response_time_ms=elapsed_ms)
            return audio
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["tts_ms"] = elapsed_ms
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
            audio = await asyncio.to_thread(generate_tts, text, language)
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["tts_ms"] = elapsed_ms
            log_event("tts_service_async_success", endpoint="tts_service", status="success", response_time_ms=elapsed_ms)
            return audio
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["tts_ms"] = elapsed_ms
            log_event("tts_service_async_failure", level="error", endpoint="tts_service", status="failure", error_type=type(exc).__name__, response_time_ms=elapsed_ms)
            raise

    async def stream_synthesize_async(self, text: str, language: str, *, interrupted: Callable[[], bool] | None = None, timings: dict | None = None) -> AsyncIterator[bytes]:
        overall_start = time.perf_counter()
        chunks = split_tts_chunks(text)
        for chunk in chunks:
            if interrupted and interrupted():
                break
            data = await asyncio.to_thread(generate_tts_bytes, chunk, language)
            if data:
                yield data
        if timings is not None:
            timings["tts_stream_ms"] = round((time.perf_counter() - overall_start) * 1000.0, 2)
