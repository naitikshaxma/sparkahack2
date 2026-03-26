import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..application.use_cases.intent.detect_intent import detect_intent as detect_intent_use_case
from ..application.use_cases.intent.detect_intent import detect_intent_legacy as detect_intent_legacy_use_case
from ..container import inject_container
from ..infrastructure.session.session_store import get_session, update_session
from ..models.api_models import IntentRequest
from ..utils.language import detect_input_language
from .response_utils import standardized_success


router = APIRouter(tags=["intent"])
USE_NEW_INTENT_UC = (os.getenv("USE_NEW_INTENT_UC") or "1").strip().lower() not in {"0", "false", "no", "off"}


@router.post("/intent")
async def detect_intent(payload: IntentRequest, request: Request, debug: bool = Query(False), container=Depends(inject_container)):
    client_ip = request.client.host if request.client else "unknown"
    validation = container.input_validator.validate_input(payload.text, client_ip=client_ip, endpoint=request.url.path)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.rejected_reason or "Invalid input.")

    timings = getattr(request.state, "timings", {})
    if USE_NEW_INTENT_UC is True:
        result = await detect_intent_use_case(
            text=validation.sanitized_text,
            normalized_text=validation.normalized_text,
            session_id=payload.session_id,
            debug=debug,
            intent_service=container.intent_service,
            timings=timings,
            get_session_fn=get_session,
            update_session_fn=update_session,
        )
    else:
        result = await detect_intent_legacy_use_case(
            text=validation.sanitized_text,
            normalized_text=validation.normalized_text,
            session_id=payload.session_id,
            debug=debug,
            intent_service=container.intent_service,
            timings=timings,
            get_session_fn=get_session,
            update_session_fn=update_session,
        )

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
