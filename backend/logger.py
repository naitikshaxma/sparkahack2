from __future__ import annotations

import json
import logging
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


_REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="")
_ENDPOINT: ContextVar[str] = ContextVar("endpoint", default="")


def configure_logging() -> None:
    logger = logging.getLogger("voice_os")
    if logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False


def set_request_context(request_id: str, endpoint: str) -> None:
    _REQUEST_ID.set(request_id or "")
    _ENDPOINT.set(endpoint or "")


def clear_request_context() -> None:
    _REQUEST_ID.set("")
    _ENDPOINT.set("")


def get_request_context() -> dict[str, str]:
    return {
        "request_id": _REQUEST_ID.get(),
        "endpoint": _ENDPOINT.get(),
    }


def _base_payload(**fields: Any) -> dict[str, Any]:
    context = get_request_context()
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": fields.pop("request_id", context.get("request_id", "")),
        "endpoint": fields.pop("endpoint", context.get("endpoint", "")),
        "intent": fields.pop("intent", None),
        "confidence": fields.pop("confidence", None),
        "user_input_length": fields.pop("user_input_length", None),
        "response_time_ms": fields.pop("response_time_ms", None),
        "status": fields.pop("status", None),
        "error_type": fields.pop("error_type", None),
    }
    payload.update(fields)
    return payload


def log_event(event: str, *, level: str = "info", **fields: Any) -> None:
    configure_logging()
    logger = logging.getLogger("voice_os")
    payload = _base_payload(event=event, **fields)
    message = json.dumps(payload, ensure_ascii=False)

    level_name = (level or "info").lower()
    if level_name == "debug":
        logger.debug(message)
    elif level_name == "warning":
        logger.warning(message)
    elif level_name == "error":
        logger.error(message)
    else:
        logger.info(message)


def log_exception(error: Exception, *, safe_context: dict[str, Any] | None = None, **fields: Any) -> None:
    payload = {
        "stack_trace": traceback.format_exc(),
        "safe_context": safe_context or {},
    }
    payload.update(fields)
    log_event(
        "exception",
        level="error",
        status="failure",
        error_type=type(error).__name__,
        **payload,
    )
