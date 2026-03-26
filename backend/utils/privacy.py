import re
from typing import Any, Dict, List


AADHAAR_RE = re.compile(r"(?<!\d)(\d{4})(\d{4})(\d{4})(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)(\d{2})(\d{6})(\d{2})(?!\d)")
ALLOWED_PROFILE_FIELDS = {"full_name", "phone", "aadhaar_number", "annual_income"}


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def mask_aadhaar(value: str) -> str:
    digits = digits_only(value)
    if len(digits) == 12:
        return f"{digits[:4]}****{digits[-4:]}"
    if len(digits) >= 8:
        return f"{digits[:4]}****{digits[-4:]}"
    return digits


def mask_phone(value: str) -> str:
    digits = digits_only(value)
    if len(digits) == 10:
        return f"{digits[:2]}******{digits[-2:]}"
    return digits


def redact_sensitive_text(text: str) -> str:
    if not text:
        return text
    redacted = AADHAAR_RE.sub(r"\1****\3", text)
    redacted = PHONE_RE.sub(r"\1******\3", redacted)
    return redacted


def sanitize_profile_for_storage(profile: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key in ALLOWED_PROFILE_FIELDS:
        value = profile.get(key)
        if value is None:
            cleaned[key] = None
            continue
        text_value = str(value).strip()
        if key == "aadhaar_number":
            cleaned[key] = mask_aadhaar(text_value)
        else:
            cleaned[key] = text_value
    return cleaned


def sanitize_profile_for_response(profile: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = sanitize_profile_for_storage(profile)
    if cleaned.get("phone"):
        cleaned["phone"] = mask_phone(str(cleaned["phone"]))
    return cleaned


def sanitize_history_for_storage(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    cleaned_history: List[Dict[str, str]] = []
    for item in history or []:
        role = str(item.get("role") or "assistant")
        content = redact_sensitive_text(str(item.get("content") or ""))
        cleaned_history.append({"role": role, "content": content})
    return cleaned_history[-10:]


def _sanitize_semantic_memory(memory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for item in memory or []:
        if not isinstance(item, dict):
            continue

        entities = item.get("entities")
        if not isinstance(entities, dict):
            entities = {}

        schemes = [str(s).strip() for s in (entities.get("schemes") or []) if str(s).strip()]
        numbers: List[str] = []
        for raw in entities.get("numbers") or []:
            digits = digits_only(str(raw))
            if not digits:
                continue
            if len(digits) >= 8:
                numbers.append(mask_aadhaar(digits))
            else:
                numbers.append(digits)

        cleaned.append(
            {
                "ts": item.get("ts"),
                "intent": str(item.get("intent") or "").strip(),
                "entities": {"schemes": schemes, "numbers": numbers},
                "user_input": redact_sensitive_text(str(item.get("user_input") or "")),
                "assistant_summary": redact_sensitive_text(str(item.get("assistant_summary") or "")),
            }
        )
    return cleaned


def sanitize_session_payload(session_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(session_data or {})

    user_profile = payload.get("user_profile")
    if isinstance(user_profile, dict):
        payload["user_profile"] = sanitize_profile_for_storage(user_profile)
    else:
        payload["user_profile"] = {}

    history = payload.get("conversation_history")
    if isinstance(history, list):
        payload["conversation_history"] = sanitize_history_for_storage(history)
    else:
        payload["conversation_history"] = []

    semantic_memory = payload.get("semantic_memory")
    if isinstance(semantic_memory, list):
        payload["semantic_memory"] = _sanitize_semantic_memory(semantic_memory)
    elif "semantic_memory" in payload:
        payload["semantic_memory"] = []

    # Do not persist raw OCR payloads.
    payload.pop("ocr_text", None)
    payload.pop("raw_ocr_text", None)

    return payload
