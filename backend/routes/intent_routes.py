from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..container import inject_container
from ..models.api_models import IntentRequest
from ..utils.language import detect_input_language
from ..utils.session_manager import get_session
from .response_utils import standardized_success


router = APIRouter(tags=["intent"])


@router.post("/intent")
async def detect_intent(payload: IntentRequest, request: Request, debug: bool = Query(False), container=Depends(inject_container)):
    client_ip = request.client.host if request.client else "unknown"
    validation = container.input_validator.validate_input(payload.text, client_ip=client_ip, endpoint=request.url.path)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid input.")

    timings = getattr(request.state, "timings", {})
    result = await container.intent_service.detect_async(text=validation.sanitized_text, debug=debug, timings=timings)

    lowered = validation.normalized_text.lower()
    if lowered in {"haan", "yes", "continue"} and (payload.session_id or "").strip():
        session = get_session(payload.session_id.strip())
        previous_intent = (session.get("last_intent") or "").strip()
        if previous_intent:
            result["intent"] = previous_intent
            result["confidence"] = max(float(result.get("confidence") or 0.0), 95.0)
            if debug:
                result["debug"] = {
                    **(result.get("debug") or {}),
                    "context_used": True,
                    "inferred_from_previous_intent": True,
                }

    request.state.intent = result.get("intent")
    request.state.confidence = result.get("confidence")
    request.state.user_input_length = len(validation.normalized_text)
    if debug:
        result["debug"] = {
            **(result.get("debug") or {}),
            "normalized_input": validation.normalized_text,
            "detected_language": detect_input_language(validation.normalized_text),
            "processing_times": timings,
        }
    return standardized_success(result)
