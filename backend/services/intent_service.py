import time
import asyncio
from typing import Any, Dict, Tuple

from backend.infrastructure.ml.bert_service import predict_intent_detailed
from ..intents import (
    INTENT_GENERAL_QUERY,
    INTENT_SCHEME_QUERY,
    get_flexible_intent_threshold,
    keyword_intent_signal,
    normalize_intent,
)
from backend.core.logger import log_event
from backend.core.metrics import record_fallback
from ..text_normalizer import normalize_for_intent


CORRECTION_MARKERS = {
    "wrong",
    "change",
    "edit",
    "update",
    "not correct",
    "गलत",
    "बदल",
    "सुधार",
    "change it",
}


def _classify_conversation_intent(text: str, model_intent: str, model_conf: float) -> Tuple[str, float]:
    query = (text or "").strip().lower()
    if any(token in query for token in CORRECTION_MARKERS):
        return "correction", max(0.78, float(model_conf))

    intent = (model_intent or "").strip().lower()
    if any(tag in intent for tag in {"scheme", "query", "info", "information"}):
        return "info", float(model_conf)
    if any(tag in intent for tag in {"apply", "action", "start", "form"}):
        return "apply", float(model_conf)

    if len(query.split()) <= 1:
        return "unknown", min(0.4, float(model_conf))
    return "unknown", float(model_conf)


def _combine_signals(model_intent: str, model_conf: float, text: str) -> Dict[str, Any]:
    canonical_model_intent, _ = normalize_intent(model_intent, default=INTENT_GENERAL_QUERY)
    keyword_intent, keyword_conf, keyword_hit = keyword_intent_signal(text)

    selected_intent = canonical_model_intent
    selected_conf = float(model_conf)
    source = "model"

    # Keywords have higher precision for short or vague user utterances.
    if keyword_hit:
        if keyword_intent != canonical_model_intent:
            selected_intent = keyword_intent
            selected_conf = max(float(model_conf), float(keyword_conf))
            source = "keyword_override"
        else:
            selected_conf = max(float(model_conf), float(keyword_conf))
            source = "model+keyword"

    threshold = get_flexible_intent_threshold(selected_intent, text)
    fallback_used = False
    fallback_reason = ""
    if selected_conf < threshold:
        # Keep scheme/general queries available for graceful clarification responses.
        if keyword_hit and keyword_intent in {INTENT_SCHEME_QUERY, INTENT_GENERAL_QUERY}:
            selected_intent = keyword_intent
            selected_conf = max(selected_conf, threshold)
            source = "keyword_soft_recovery"
        elif selected_intent not in {INTENT_SCHEME_QUERY, INTENT_GENERAL_QUERY}:
            selected_intent = INTENT_SCHEME_QUERY
            selected_conf = max(0.35, selected_conf)
            source = "safe_info_fallback"
            fallback_used = True
            fallback_reason = "low_confidence_action_intent"

    return {
        "intent": selected_intent,
        "confidence": float(selected_conf),
        "threshold": float(threshold),
        "fallback_used": bool(fallback_used),
        "fallback_reason": fallback_reason,
        "source": source,
        "keyword_signal": {
            "hit": keyword_hit,
            "intent": keyword_intent,
            "confidence": float(keyword_conf),
        },
    }


class IntentService:
    def detect(self, text: str, debug: bool = False, timings: dict | None = None) -> Dict[str, Any]:
        start = time.perf_counter()
        log_event("intent_service_start", endpoint="intent_service", status="success", user_input_length=len(text or ""))
        try:
            normalized = normalize_for_intent(text)
            model_decision = predict_intent_detailed(normalized.intent_text)
            combined = _combine_signals(
                model_intent=str(model_decision.get("primary_intent", INTENT_GENERAL_QUERY)),
                model_conf=float(model_decision.get("confidence", 0.0)),
                text=normalized.intent_text,
            )

            decision = {
                **model_decision,
                "primary_intent": combined["intent"],
                "confidence": combined["confidence"],
                "fallback_used": bool(model_decision.get("fallback_used") or combined["fallback_used"]),
                "fallback_reason": combined["fallback_reason"] or model_decision.get("fallback_reason", ""),
                "threshold": combined["threshold"],
                "resolution_source": combined["source"],
                "keyword_signal": combined["keyword_signal"],
                "normalized_input": normalized.intent_text,
                "normalized_language": normalized.language,
            }

            convo_intent, convo_conf = _classify_conversation_intent(
                normalized.intent_text,
                str(decision.get("primary_intent") or ""),
                float(decision.get("confidence") or 0.0),
            )
            decision["conversation_intent"] = convo_intent
            decision["conversation_confidence"] = round(max(0.0, min(1.0, convo_conf)), 4)

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
                    "fallback_reason": decision.get("fallback_reason"),
                    "context_used": decision.get("context_used"),
                    "intent_version": decision.get("intent_version"),
                    "resolution_source": decision.get("resolution_source"),
                    "keyword_signal": decision.get("keyword_signal"),
                    "normalized_input": decision.get("normalized_input"),
                    "normalized_language": decision.get("normalized_language"),
                    "conversation_intent": decision.get("conversation_intent"),
                    "conversation_confidence": decision.get("conversation_confidence"),
                },
            }

        return {
            "intent": decision["primary_intent"],
            "confidence": round(float(decision["confidence"]) * 100.0, 2),
            "conversation_intent": decision.get("conversation_intent"),
            "conversation_confidence": round(float(decision.get("conversation_confidence", 0.0)) * 100.0, 2),
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
