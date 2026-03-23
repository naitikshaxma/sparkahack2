import time
import asyncio
from typing import Any, Dict

from ..bert_service import predict_intent_detailed
from ..logger import log_event
from ..metrics import record_fallback


class IntentService:
    def detect(self, text: str, debug: bool = False, timings: dict | None = None) -> Dict[str, Any]:
        start = time.perf_counter()
        log_event("intent_service_start", endpoint="intent_service", status="success", user_input_length=len(text or ""))
        try:
            decision = predict_intent_detailed(text)
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["intent_classification_ms"] = elapsed_ms
            if decision.get("fallback_used"):
                record_fallback()
            log_event(
                "intent_service_success",
                endpoint="intent_service",
                status="success",
                response_time_ms=elapsed_ms,
                intent=decision.get("primary_intent"),
                confidence=round(float(decision.get("confidence", 0.0)) * 100.0, 2),
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None:
                timings["intent_classification_ms"] = elapsed_ms
            log_event(
                "intent_service_failure",
                level="error",
                endpoint="intent_service",
                status="failure",
                error_type=type(exc).__name__,
                response_time_ms=elapsed_ms,
            )
            raise

        if debug:
            return {
                "intent": decision["primary_intent"],
                "secondary_intents": decision.get("secondary_intents", []),
                "confidence": round(float(decision["confidence"]) * 100.0, 2),
                "debug": {
                    "raw_model_output": decision.get("raw_model_output"),
                    "normalized_intent": decision.get("normalized_intent"),
                    "fallback_used": decision.get("fallback_used"),
                    "context_used": decision.get("context_used"),
                    "intent_version": decision.get("intent_version"),
                },
            }

        return {
            "intent": decision["primary_intent"],
            "confidence": round(float(decision["confidence"]) * 100.0, 2),
        }

    async def detect_async(self, text: str, debug: bool = False, timings: dict | None = None) -> Dict[str, Any]:
        start = time.perf_counter()
        log_event("intent_service_async_start", endpoint="intent_service", status="success", user_input_length=len(text or ""))
        try:
            result = await asyncio.to_thread(self.detect, text, debug, timings)
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None and "intent_classification_ms" not in timings:
                timings["intent_classification_ms"] = elapsed_ms
            log_event("intent_service_async_success", endpoint="intent_service", status="success", response_time_ms=elapsed_ms, intent=result.get("intent"), confidence=result.get("confidence"))
            return result
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
            if timings is not None and "intent_classification_ms" not in timings:
                timings["intent_classification_ms"] = elapsed_ms
            log_event("intent_service_async_failure", level="error", endpoint="intent_service", status="failure", error_type=type(exc).__name__, response_time_ms=elapsed_ms)
            raise
