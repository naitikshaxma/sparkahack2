import time

import asyncio

from ..logger import log_event
from ..whisper_service import transcribe_audio


class STTService:
    def transcribe(self, audio_bytes: bytes, language: str, suffix: str, timings: dict | None = None) -> str:
        start = time.perf_counter()
        log_event("stt_service_start", endpoint="stt_service", status="success")
        try:
            transcript = transcribe_audio(audio_bytes, language=language, source_suffix=suffix)
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["stt_ms"] = elapsed_ms
            log_event("stt_service_success", endpoint="stt_service", status="success", response_time_ms=elapsed_ms)
            return transcript
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["stt_ms"] = elapsed_ms
            log_event(
                "stt_service_failure",
                level="error",
                endpoint="stt_service",
                status="failure",
                error_type=type(exc).__name__,
                response_time_ms=elapsed_ms,
            )
            raise

    async def transcribe_async(self, audio_bytes: bytes, language: str, suffix: str, timings: dict | None = None) -> str:
        start = time.perf_counter()
        log_event("stt_service_async_start", endpoint="stt_service", status="success")
        try:
            transcript = await asyncio.to_thread(transcribe_audio, audio_bytes, language, suffix)
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["stt_ms"] = elapsed_ms
            log_event("stt_service_async_success", endpoint="stt_service", status="success", response_time_ms=elapsed_ms)
            return transcript
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["stt_ms"] = elapsed_ms
            log_event("stt_service_async_failure", level="error", endpoint="stt_service", status="failure", error_type=type(exc).__name__, response_time_ms=elapsed_ms)
            raise
