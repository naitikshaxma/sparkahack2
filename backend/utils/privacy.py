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

    # Do not persist raw OCR payloads.
    payload.pop("ocr_text", None)
    payload.pop("raw_ocr_text", None)

    return payload