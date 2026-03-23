import json
from typing import Any, Dict

from openai import OpenAI

from ..config import get_settings
from ..utils.language import normalize_language_code
from ..utils.form_schema import get_field_question, get_next_field
from ..utils.privacy import redact_sensitive_text, sanitize_profile_for_response

SETTINGS = get_settings()

MODEL_NAME = SETTINGS.openai_chat_model
SYSTEM_PROMPT = (
    "You are a government scheme assistant. "
    "Ask ONLY one question at a time. "
    "Always respond ONLY in the user's selected language code provided in session context. "
    "Respond ONLY in {language}. Do not mix languages. "
    "Do NOT mix languages in the same reply. "
    "If language is Hindi, respond fully in Hindi using Devanagari script only. "
    "If language is English, respond fully in English. "
    "Never transliterate or switch script unless that is the selected language. "
    "NEVER use technical field keys like annual_income in user-facing text. "
    "Validate conversationally. If invalid, explain briefly and ask again. "
    "Keep replies short and human-like. Always return JSON only. "
    "Response JSON keys must be exactly: field_name, field_value, validation_passed, "
    "validation_error, next_question_text, session_complete."
)


_client: OpenAI | None = None
MAX_HISTORY_MESSAGES = 10


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=SETTINGS.openai_api_key)
    return _client


def _trim_history(session: Dict[str, Any]) -> None:
    history = session.setdefault("conversation_history", [])
    if len(history) > MAX_HISTORY_MESSAGES:
        session["conversation_history"] = history[-MAX_HISTORY_MESSAGES:]


def _append_history(session: Dict[str, Any], role: str, content: str) -> None:
    if not content:
        return
    session.setdefault("conversation_history", []).append({"role": role, "content": redact_sensitive_text(content)})
    _trim_history(session)


def _fallback_agent_response(session: Dict[str, Any]) -> Dict[str, Any]:
    next_field = get_next_field(session)
    language = normalize_language_code(session.get("language", "en"), default="en")
    if next_field is None:
        complete_message = get_field_question(None, language)
        return {
            "field_name": None,
            "field_value": None,
            "validation_passed": True,
            "validation_error": None,
            "next_question_text": complete_message,
            "session_complete": True,
        }

    return {
        "field_name": next_field,
        "field_value": None,
        "validation_passed": True,
        "validation_error": None,
        "next_question_text": get_field_question(next_field, language),
        "session_complete": False,
    }


def run_agent(session: Dict[str, Any], user_input: str, store_history: bool = True) -> Dict[str, Any]:
    current_field = session.get("next_field") or get_next_field(session)
    language = normalize_language_code(session.get("language", "en"), default="en")
    history = session.get("conversation_history", [])[-10:]

    # Keep only valid role/content history to avoid malformed chat payloads.
    history_messages = [
        {
            "role": msg.get("role"),
            "content": msg.get("content", ""),
        }
        for msg in history
        if msg.get("role") in {"user", "assistant"} and isinstance(msg.get("content"), str)
    ]

    payload = {
        "language": language,
        "current_field": current_field,
        "field_completion": session.get("field_completion", {}),
        "user_profile": sanitize_profile_for_response(session.get("user_profile", {})),
        "session_complete": session.get("session_complete", False),
        "user_input": user_input,
    }

    user_prompt = {
        "role": "user",
        "content": (
            f"Selected language code: {language}. next_question_text must be strictly in this language only.\n"
            f"Respond ONLY in {language}. Do not mix languages.\n"
            "If language is hi, output only pure Hindi in Devanagari script.\n"
            "Return JSON using keys: field_name, field_value, validation_passed, "
            "validation_error, next_question_text, session_complete.\n"
            f"Session context: {json.dumps(payload, ensure_ascii=False)}"
        ),
    }

    try:
        response = _get_client().chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history_messages, user_prompt],
            temperature=0.1,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        next_question = parsed.get("next_question_text") or get_field_question(current_field, language)
        validation_error = parsed.get("validation_error")
        if store_history:
            if user_input.strip():
                _append_history(session, "user", user_input.strip())
            _append_history(session, "assistant", next_question)

        return {
            "field_name": parsed.get("field_name"),
            "field_value": parsed.get("field_value"),
            "validation_passed": bool(parsed.get("validation_passed", True)),
            "validation_error": validation_error,
            "next_question_text": next_question,
            "session_complete": bool(parsed.get("session_complete", False)),
        }
    except Exception:
        fallback = _fallback_agent_response(session)
        if store_history:
            if user_input.strip():
                _append_history(session, "user", user_input.strip())
            _append_history(session, "assistant", fallback["next_question_text"])
        return fallback
