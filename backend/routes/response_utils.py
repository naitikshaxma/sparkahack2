from typing import Any, Dict


def standardized_success(payload: Any) -> Dict[str, Any]:
    envelope: Dict[str, Any] = {
        "success": True,
        "data": payload,
        "error": None,
    }
    if isinstance(payload, dict):
        envelope.update(payload)
    return envelope


def standardized_error(message: str, *, data: Any = None) -> Dict[str, Any]:
    if data is None:
        data = {}
    return {
        "success": False,
        "data": data,
        "error": message,
        "detail": message,
    }
