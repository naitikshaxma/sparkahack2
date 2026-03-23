import re
import logging
import time
from typing import Any, Dict, List, Optional

from ..bert_service import predict_intent_detailed
from ..flow_engine import generate_response
from ..intent_router import detect_intent_and_mode, is_followup_info_query
from ..intents import ACTION_INTENTS, INFO_INTENTS
from ..rag_service import recommend_schemes
from ..response_formatter import (
    build_quick_actions,
    build_recommendation_quick_actions,
    build_scheme_details,
    format_info_text,
    format_short_voice_text,
)
from ..logger import log_event
from ..utils.language import normalize_language_code
from ..utils.privacy import redact_sensitive_text, sanitize_profile_for_response
from ..utils.form_schema import LOAN_FIELDS, get_field_question, get_next_field
from ..utils.session_manager import create_session, delete_session, get_session, update_session
from ..utils.validator import validate
from .agent_service import run_agent


logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 10
MAX_SEMANTIC_MEMORY_ITEMS = 12
AMBIGUOUS_WORDS = {"maybe", "around", "approx", "lagbhag", "approximately"}
YES_WORDS = {"yes", "haan", "ha", "ji", "correct", "sahi", "right"}
NO_WORDS = {"no", "nahin", "nahi", "galat", "wrong", "not correct"}
UNCLEAR_WORDS = {"hmm", "uh", "hello", "helo", "sun", "listen", "something", "kuch", "pata nahi", "not sure"}

FIELD_LABELS = {
    "full_name": {"en": "Full Name", "hi": "पूरा नाम"},
    "phone": {"en": "Phone", "hi": "मोबाइल नंबर"},
    "aadhaar_number": {"en": "Aadhaar", "hi": "आधार नंबर"},
    "annual_income": {"en": "Annual Income", "hi": "वार्षिक आय"},
}

SCHEME_ENTITY_RE = re.compile(r"\b(pm\s*kisan|ayushman|pmay|pension|loan)\b", re.IGNORECASE)
NUMBER_ENTITY_RE = re.compile(r"\b\d{4,}\b")


def _trim_history(session: Dict[str, Any]) -> None:
    history = session.setdefault("conversation_history", [])
    if len(history) > MAX_HISTORY_MESSAGES:
        session["conversation_history"] = history[-MAX_HISTORY_MESSAGES:]


def _append_history(session: Dict[str, Any], role: str, content: str) -> None:
    if not content:
        return
    session.setdefault("conversation_history", []).append({"role": role, "content": redact_sensitive_text(content)})
    _trim_history(session)


def _extract_entities(text: str) -> Dict[str, List[str]]:
    content = (text or "").strip()
    if not content:
        return {"schemes": [], "numbers": []}

    schemes = [match.group(1).strip().lower() for match in SCHEME_ENTITY_RE.finditer(content)]
    numbers = [match.group(0) for match in NUMBER_ENTITY_RE.finditer(content)]
    return {
        "schemes": sorted(set(schemes))[:5],
        "numbers": sorted(set(numbers))[:5],
    }


def _update_semantic_memory(session: Dict[str, Any], user_input: str, response: Dict[str, Any], intent: str) -> None:
    entities = _extract_entities(user_input)
    semantic = session.setdefault("semantic_memory", [])
    semantic.append(
        {
            "ts": int(time.time()),
            "intent": (intent or "").strip(),
            "entities": entities,
            "user_input": (user_input or "").strip()[:200],
            "assistant_summary": (response.get("voice_text") or response.get("response_text") or "")[:240],
        }
    )
    session["semantic_memory"] = semantic[-MAX_SEMANTIC_MEMORY_ITEMS:]
    # Fast-access context hints for future turns.
    if entities.get("schemes"):
        session["memory_last_scheme_entities"] = entities["schemes"]
    session["memory_last_intent"] = (intent or "").strip()


def update_semantic_memory(session: Dict[str, Any], user_input: str, response: Dict[str, Any], intent: str) -> None:
    _update_semantic_memory(session, user_input, response, intent)


def _build_response(
    session_id: str,
    response_text: str,
    field_name: Optional[str],
    validation_passed: bool,
    session_complete: bool,
    validation_error: Optional[str] = None,
    mode: str = "action",
    action: Optional[str] = None,
    session: Optional[Dict[str, Any]] = None,
    scheme_details: Optional[Dict[str, Any]] = None,
    voice_text: Optional[str] = None,
    quick_actions: Optional[List[Dict[str, str]]] = None,
    recommended_schemes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    steps_done = 0
    steps_total = len(LOAN_FIELDS)
    if session:
        completion = session.get("field_completion", {})
        steps_done = sum(1 for field in LOAN_FIELDS if completion.get(field))

    language = normalize_language_code((session or {}).get("language", "en") if session else "en", default="en")
    completed_fields = []
    if session:
        completion = session.get("field_completion", {})
        for field in LOAN_FIELDS:
            if completion.get(field):
                completed_fields.append(FIELD_LABELS.get(field, {}).get(language, field))

    return {
        "session_id": session_id,
        "response_text": response_text,
        "voice_text": voice_text or format_short_voice_text(response_text, language),
        "primary_intent": (session or {}).get("last_intent"),
        "secondary_intents": (session or {}).get("last_secondary_intents", []),
        "field_name": field_name,
        "validation_passed": validation_passed,
        "validation_error": validation_error,
        "session_complete": session_complete,
        "mode": mode,
        "action": action,
        "steps_done": steps_done,
        "steps_total": steps_total,
        "completed_fields": completed_fields,
        "scheme_details": scheme_details,
        "quick_actions": quick_actions or [],
        "recommended_schemes": recommended_schemes or [],
        "user_profile": sanitize_profile_for_response((session or {}).get("user_profile", {})),
        "intent_debug": (session or {}).get("_intent_debug"),
    }


def _detect_language(user_input: str) -> str:
    text = (user_input or "").strip().lower()
    hindi_hinglish_tokens = {
        "kya",
        "mera",
        "meri",
        "aap",
        "kripya",
        "haan",
        "nahi",
        "ji",
        "aadhaar",
        "batayein",
        "wapas",
        "jao",
    }
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    if any(token in text for token in hindi_hinglish_tokens):
        return "hi"
    return "en"


def _is_restart_command(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    return text in {"restart", "reset", "start over", "new form", "phir se", "dobara"}


def _is_go_back_command(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    return text in {"go back", "back", "wapas jao", "pichla", "previous"}


def _is_skip_command(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    return text in {"skip", "chhodo", "chod do", "aage bado", "next"}


def _resolve_quick_action_input(user_input: str, language: str, session: Dict[str, Any]) -> str:
    raw = (user_input or "").strip()
    if not raw:
        return raw

    lowered = raw.lower()
    if lowered.startswith("recommend_scheme:"):
        scheme = raw.split(":", 1)[1].strip()
        return scheme or raw

    last_scheme = session.get("last_scheme")
    mapping = {
        "need_information": "जानकारी चाहिए" if language == "hi" else "Need information",
        "start_application": "आवेदन शुरू करें" if language == "hi" else "Start application",
        "apply_now": "आवेदन शुरू करें" if language == "hi" else "Apply now",
        "more_info": "और जानकारी" if language == "hi" else "More info",
        "show_eligibility": (
            f"{last_scheme} पात्रता" if language == "hi" and last_scheme else
            f"{last_scheme} eligibility" if last_scheme else
            "पात्रता बताएं" if language == "hi" else
            "Show eligibility"
        ),
        "confirm_yes": "हाँ" if language == "hi" else "yes",
        "confirm_no": "नहीं" if language == "hi" else "no",
        "next_step": "next",
        "application_status": "status",
        "restart_session": "restart",
        "auto_fill_form": "auto fill form",
    }
    return mapping.get(lowered, raw)


def _reset_session_state(session: Dict[str, Any]) -> Dict[str, Any]:
    # Kept for compatibility, but hard reset now uses delete + create.
    field_completion = {field: False for field in LOAN_FIELDS}
    session["user_profile"] = {}
    session["field_completion"] = field_completion
    session["next_field"] = LOAN_FIELDS[0] if LOAN_FIELDS else None
    session["session_complete"] = False
    session["conversation_history"] = []
    session["last_completed_field_index"] = -1
    session["confirmation_done"] = False
    session["confirmation_state"] = "pending"
    return session


def _normalize_session_state(session: Dict[str, Any]) -> Dict[str, Any]:
    # Protect against corrupted or partially missing session payloads.
    session.setdefault("user_profile", {})
    session.setdefault("field_completion", {field: False for field in LOAN_FIELDS})
    for field in LOAN_FIELDS:
        session["field_completion"].setdefault(field, False)

    session.setdefault("conversation_history", [])
    session.setdefault("session_complete", False)
    session.setdefault("confirmation_done", False)
    session.setdefault("confirmation_state", "pending")
    session.setdefault("last_completed_field_index", -1)
    session.setdefault("ocr_extracted", {"fields": [], "confidence": 0.0})
    session.setdefault("ocr_confirmation_pending", False)
    session.setdefault("ocr_pending_fields", [])
    session.setdefault("action_confirmation_pending", False)

    next_field = session.get("next_field")
    if next_field not in LOAN_FIELDS and next_field is not None:
        next_field = get_next_field(session)
    if next_field is None and not session.get("session_complete", False):
        next_field = get_next_field(session)
    session["next_field"] = next_field
    return session


def merge_ocr_data(session: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    session = _normalize_session_state(session)
    updated_fields = []
    user_profile = session.setdefault("user_profile", {})
    field_completion = session.setdefault("field_completion", {})

    for field in ["full_name", "aadhaar_number"]:
        value = extracted_data.get(field)
        if value is None:
            continue
        if field_completion.get(field, False) or user_profile.get(field):
            continue

        is_valid, normalized_value, _ = validate(field, str(value))
        if not is_valid:
            continue

        user_profile[field] = normalized_value
        field_completion[field] = True
        updated_fields.append(field)

    if updated_fields:
        session["last_completed_field_index"] = max(LOAN_FIELDS.index(f) for f in updated_fields)

    confidence_raw = extracted_data.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.0

    session["ocr_extracted"] = {"fields": updated_fields, "confidence": confidence}
    session["ocr_pending_fields"] = list(updated_fields)
    session["ocr_confirmation_pending"] = bool(updated_fields)
    session["next_field"] = get_next_field(session)
    session["session_complete"] = False
    session["confirmation_done"] = False
    session["confirmation_state"] = "pending"
    return session


def _build_ocr_confirmation_text(session: Dict[str, Any], ocr_data: Dict[str, Any], language: str) -> str:
    profile = session.get("user_profile", {})
    name = profile.get("full_name") or "-"
    aadhaar = profile.get("aadhaar_number") or "-"
    dob = ocr_data.get("date_of_birth") or "-"
    if language == "hi":
        return (
            "मैंने आपका दस्तावेज़ स्कैन किया:\n"
            f"नाम: {name}\n"
            f"आधार: {aadhaar}\n"
            f"जन्म तिथि: {dob}\n"
            "क्या यह सही है?"
        )
    return (
        "I scanned your document:\n"
        f"Name: {name}\n"
        f"Aadhaar: {aadhaar}\n"
        f"Date of Birth: {dob}\n"
        "Is this correct?"
    )


def get_ocr_confirmation_message(session: Dict[str, Any], ocr_data: Dict[str, Any], language: str) -> str:
    return _build_ocr_confirmation_text(session, ocr_data, language)


def _handle_ocr_confirmation(session_id: str, session: Dict[str, Any], user_input: str, language: str) -> Dict[str, Any]:
    cleaned_input = (user_input or "").strip().lower()

    if cleaned_input in YES_WORDS:
        session["ocr_confirmation_pending"] = False
        session["ocr_pending_fields"] = []

        next_field = get_next_field(session)
        session["next_field"] = next_field
        if next_field is None:
            session["confirmation_state"] = "pending"
            confirmation_text = _build_confirmation_summary(session, language)
            _append_history(session, "assistant", confirmation_text)
            update_session(session_id, session)
            return _build_response(session_id, confirmation_text, None, True, False, None, session=session)

        question = get_field_question(next_field, language)
        _append_history(session, "assistant", question)
        update_session(session_id, session)
        return _build_response(session_id, question, next_field, True, False, None, session=session)

    if cleaned_input in NO_WORDS or _is_go_back_command(cleaned_input) or "correct" in cleaned_input:
        for field in session.get("ocr_pending_fields", []):
            session.setdefault("user_profile", {}).pop(field, None)
            session.setdefault("field_completion", {})[field] = False

        session["ocr_confirmation_pending"] = False
        session["ocr_pending_fields"] = []
        session["next_field"] = get_next_field(session)
        session["session_complete"] = False

        next_field = session.get("next_field")
        question = get_field_question(next_field, language)
        guide = (
            f"ठीक है, हम इसे मैन्युअली भरते हैं। {question}"
            if language == "hi"
            else f"Sure, let us fill it manually. {question}"
        )
        _append_history(session, "assistant", guide)
        update_session(session_id, session)
        return _build_response(session_id, guide, next_field, True, False, None, session=session)

    prompt = (
        "यदि विवरण सही हैं तो कृपया हाँ कहें, अन्यथा नहीं कहें।"
        if language == "hi"
        else "Please reply yes if details are correct, otherwise say no."
    )
    _append_history(session, "assistant", prompt)
    update_session(session_id, session)
    return _build_response(session_id, prompt, None, False, False, "ocr_confirmation_pending", session=session)


def _is_ambiguous_input(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    return any(word in text for word in AMBIGUOUS_WORDS)


def _is_unclear_input(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    if len(text) <= 2:
        return True
    return text in UNCLEAR_WORDS


def _looks_like_field_value(field_name: Optional[str], user_input: str) -> bool:
    value = (user_input or "").strip()
    if not value or not field_name:
        return False

    if field_name == "phone":
        return bool(re.fullmatch(r"\D*\d\D*\d\D*\d\D*\d\D*\d\D*\d\D*\d\D*\d\D*\d\D*\d\D*", value))

    if field_name == "aadhaar_number":
        digits = re.sub(r"\D", "", value)
        return len(digits) == 12

    if field_name == "annual_income":
        candidate = value.replace(",", "")
        return bool(re.fullmatch(r"\d+(\.\d+)?", candidate))

    if field_name == "full_name":
        lowered = value.lower()
        if "?" in lowered or "kya" in lowered or "what" in lowered or "scheme" in lowered or "yojana" in lowered:
            return False
        return bool(re.fullmatch(r"[A-Za-z\s.'-]{2,80}", value))

    return False


def _build_confirmation_summary(session: Dict[str, Any], language: str) -> str:
    profile = session.get("user_profile", {})
    name = profile.get("full_name") or "-"
    phone = profile.get("phone") or "-"
    aadhaar = profile.get("aadhaar_number") or "-"
    income = profile.get("annual_income") or "-"

    if language == "hi":
        return (
            f"मैं पुष्टि करता हूँ: आपका नाम {name}, मोबाइल नंबर {phone}, "
            f"आधार {aadhaar}, और वार्षिक आय {income} है। क्या यह सही है?"
        )
    return (
        f"Let me confirm: your name is {name}, phone is {phone}, Aadhaar is {aadhaar}, "
        f"and annual income is {income}. Is this correct?"
    )


def _move_to_previous_field(session: Dict[str, Any]) -> Optional[str]:
    last_index = int(session.get("last_completed_field_index", -1))
    if last_index < 0:
        return session.get("next_field")

    previous_field = LOAN_FIELDS[last_index]
    session.setdefault("user_profile", {}).pop(previous_field, None)
    session.setdefault("field_completion", {})[previous_field] = False
    session["next_field"] = previous_field
    session["session_complete"] = False
    session["confirmation_done"] = False
    session["confirmation_state"] = "pending"
    session["last_completed_field_index"] = max(-1, last_index - 1)
    return previous_field


def _confirmation_handler(
    session_id: str,
    session: Dict[str, Any],
    user_input: str,
    language: str,
) -> Dict[str, Any]:
    cleaned_input = (user_input or "").strip().lower()

    if _is_restart_command(cleaned_input):
        delete_session(session_id)
        fresh = create_session(session_id)
        fresh = _normalize_session_state(fresh)
        fresh["language"] = language
        question = get_field_question(fresh.get("next_field"), language)
        _append_history(fresh, "assistant", question)
        update_session(session_id, fresh)
        return _build_response(session_id, question, fresh.get("next_field"), True, False, None, session=fresh)

    if _is_go_back_command(cleaned_input):
        previous = _move_to_previous_field(session)
        question = get_field_question(previous, language)
        _append_history(session, "assistant", question)
        update_session(session_id, session)
        return _build_response(session_id, question, previous, True, False, None, session=session)

    if cleaned_input in YES_WORDS:
        session["confirmation_done"] = True
        session["confirmation_state"] = "confirmed"
        session["session_complete"] = True
        done_text = (
            "धन्यवाद, आपका फॉर्म पुष्टि हो गया है।"
            if language == "hi"
            else "Thank you, your form is confirmed."
        )
        _append_history(session, "assistant", done_text)
        update_session(session_id, session)
        return _build_response(session_id, done_text, None, True, True, None, session=session)

    if cleaned_input in NO_WORDS:
        session["confirmation_done"] = False
        session["confirmation_state"] = "pending"
        previous = _move_to_previous_field(session)
        question = get_field_question(previous, language)
        guide = (
            f"ठीक है, हम इसे ठीक करते हैं। {question}"
            if language == "hi"
            else f"Sure, let us correct it. {question}"
        )
        _append_history(session, "assistant", guide)
        update_session(session_id, session)
        return _build_response(session_id, guide, previous, True, False, None, session=session)

    prompt = (
        "Please reply with yes to confirm, or use go back/restart to make corrections."
        if language == "en"
        else "कृपया पुष्टि के लिए हाँ कहें, या संशोधन के लिए वापस जाएँ/पुनः प्रारंभ करें।"
    )
    _append_history(session, "assistant", prompt)
    update_session(session_id, session)
    return _build_response(session_id, prompt, None, False, False, "confirmation_pending", session=session)


def _validation_error_message(field: str, error_message: str, language: str) -> str:
    if language == "hi":
        if field == "phone":
            return "मोबाइल नंबर अमान्य है, कृपया 10 अंकों का नंबर बताएं।"
        if field == "aadhaar_number":
            return "आधार नंबर अमान्य है, कृपया 12 अंकों का आधार नंबर बताएं।"
        if field == "annual_income":
            return "आय का प्रारूप अमान्य है, कृपया केवल संख्यात्मक मान दें।"
        return f"इनपुट अमान्य है ({error_message}), कृपया दोबारा बताएं।"
    return f"Invalid input ({error_message}). Please try again."


def _clarification_message(language: str) -> str:
    if language == "hi":
        return "क्या आपको योजना की जानकारी चाहिए या अभी आवेदन शुरू करना है?"
    return "Do you want scheme information, or should I start the application now?"


def _action_start_confirmation_message(language: str) -> str:
    if language == "hi":
        return "क्या मैं आवेदन फॉर्म शुरू कर दूँ? कृपया हाँ या नहीं कहें।"
    return "Should I start the application form now? Please say yes or no."


def handle_conversation(session_id: str, user_input: str, language: Optional[str] = None, debug: bool = False) -> Dict[str, Any]:
    try:
        session = get_session(session_id)
    except Exception:
        session = create_session(session_id)

    session = _normalize_session_state(session)

    cleaned_input = (user_input or "").strip()
    if language and language.strip():
        session["language"] = normalize_language_code(language, default="en")
    elif session.get("language"):
        session["language"] = normalize_language_code(session.get("language"), default="en")
    else:
        session["language"] = normalize_language_code(_detect_language(cleaned_input), default="en")

    current_field = session.get("next_field") or get_next_field(session)
    session["next_field"] = current_field
    lang = normalize_language_code(session.get("language", "en"), default="en")
    session["language"] = lang
    cleaned_input = _resolve_quick_action_input(cleaned_input, lang, session)
    progress_started = any(session.get("field_completion", {}).get(field, False) for field in LOAN_FIELDS)
    intent_decision = predict_intent_detailed(
        cleaned_input,
        session_context={
            "last_intent": session.get("last_intent"),
            "last_action": session.get("last_action"),
        },
    )
    model_intent = intent_decision["primary_intent"]
    model_confidence = float(intent_decision["confidence"])
    model_fallback_used = bool(intent_decision["fallback_used"])
    secondary_intents = intent_decision.get("secondary_intents", [])

    detected_intent, detected_mode = detect_intent_and_mode(
        cleaned_input,
        predicted_intent=model_intent,
        confidence=model_confidence,
    )

    has_action_signal = detected_intent in ACTION_INTENTS or any(intent in ACTION_INTENTS for intent in secondary_intents)
    has_info_signal = detected_intent in INFO_INTENTS or any(intent in INFO_INTENTS for intent in secondary_intents)
    if has_action_signal and has_info_signal and not progress_started:
        detected_mode = "clarify"

    if detected_mode == "info":
        mode = "info"
        # User changed intent to information; do not keep forcing action state.
        session["action_confirmation_pending"] = False
    elif detected_mode == "action":
        mode = "action"
    elif progress_started and _looks_like_field_value(current_field, cleaned_input):
        mode = "action"
    else:
        # Unknown or unrelated inputs should not trap user in form flow.
        mode = "info"

    session["last_intent"] = model_intent
    session["last_secondary_intents"] = secondary_intents
    session["last_action"] = mode
    if debug:
        session["_intent_debug"] = intent_decision
    else:
        session.pop("_intent_debug", None)

    logger.info(
        "routing decision: session_id=%s detected_intent=%s model_intent=%s confidence=%.3f fallback_used=%s secondary_intents=%s selected_mode=%s current_field=%s progress_started=%s",
        session_id,
        detected_intent,
        model_intent,
        model_confidence,
        model_fallback_used,
        secondary_intents,
        mode,
        current_field,
        progress_started,
    )

    if _is_unclear_input(cleaned_input):
        unclear_text = (
            "मैं आपकी मदद के लिए तैयार हूँ। क्या आप योजना की जानकारी चाहते हैं या आवेदन शुरू करना चाहते हैं?"
            if lang == "hi"
            else "I am here to help. Do you want scheme information, or should I start the application?"
        )
        _append_history(session, "user", cleaned_input)
        _append_history(session, "assistant", unclear_text)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=unclear_text,
            field_name=None,
            validation_passed=False,
            validation_error="unclear_input",
            session_complete=False,
            mode="clarify",
            action="clarify_intent",
            session=session,
            quick_actions=build_quick_actions(lang, "clarify", "clarify_intent", session.get("last_scheme"), False),
            voice_text=unclear_text,
        )

    if mode == "clarify":
        response_text = _clarification_message(lang)
        _append_history(session, "user", cleaned_input)
        _append_history(session, "assistant", response_text)
        update_session(session_id, session)

        return _build_response(
            session_id=session_id,
            response_text=response_text,
            field_name=None,
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            mode="clarify",
            action="clarify_intent",
            session=session,
            quick_actions=build_quick_actions(lang, "clarify", "clarify_intent", session.get("last_scheme"), False),
        )

    if mode == "info":
        _append_history(session, "user", cleaned_input)
        query_for_rag = cleaned_input
        if session.get("last_scheme") and is_followup_info_query(cleaned_input):
            query_for_rag = f"{session.get('last_scheme')} {cleaned_input}".strip()

        rag_response, intent, _ = generate_response(language=lang, transcript=query_for_rag)
        session["last_intent"] = intent
        session["last_action"] = "info"
        response_text = format_info_text(rag_response, lang)
        _append_history(session, "assistant", response_text)

        scheme_details = build_scheme_details(intent, rag_response)
        recommendations: List[str] = []
        if scheme_details and scheme_details.get("title"):
            session["last_scheme"] = scheme_details.get("title")
        else:
            recommendations = recommend_schemes(cleaned_input, lang)
            if recommendations:
                if lang == "hi":
                    response_text = f"{response_text}\n\nआप इन योजनाओं के बारे में भी पूछ सकते हैं: {', '.join(recommendations)}"
                else:
                    response_text = f"{response_text}\n\nYou can also ask about: {', '.join(recommendations)}"

        quick_actions = (
            build_recommendation_quick_actions(recommendations, lang)
            if recommendations
            else build_quick_actions(lang, "info", "ask_to_apply_or_more_info", session.get("last_scheme"), False)
        )

        update_session(session_id, session)

        return _build_response(
            session_id=session_id,
            response_text=response_text,
            field_name=None,
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            mode="info",
            action="ask_to_apply_or_more_info",
            session=session,
            scheme_details=scheme_details,
            quick_actions=quick_actions,
            recommended_schemes=recommendations,
        )

    if mode == "action" and not progress_started:
        if session.get("action_confirmation_pending", False):
            if cleaned_input.lower() in YES_WORDS:
                session["action_confirmation_pending"] = False
            elif cleaned_input.lower() in NO_WORDS:
                session["action_confirmation_pending"] = False
                response_text = (
                    "ठीक है, पहले जानकारी देखते हैं। आप योजना का नाम बताएं या पात्रता पूछें।"
                    if lang == "hi"
                    else "Sure, let us review information first. Tell me a scheme name or ask for eligibility."
                )
                _append_history(session, "assistant", response_text)
                update_session(session_id, session)
                return _build_response(
                    session_id=session_id,
                    response_text=response_text,
                    field_name=None,
                    validation_passed=True,
                    validation_error=None,
                    session_complete=False,
                    mode="info",
                    action="ask_to_apply_or_more_info",
                    session=session,
                    quick_actions=build_quick_actions(lang, "info", "ask_to_apply_or_more_info", session.get("last_scheme"), False),
                )
            else:
                response_text = _action_start_confirmation_message(lang)
                _append_history(session, "assistant", response_text)
                update_session(session_id, session)
                return _build_response(
                    session_id=session_id,
                    response_text=response_text,
                    field_name=None,
                    validation_passed=False,
                    validation_error="action_confirmation_pending",
                    session_complete=False,
                    mode="clarify",
                    action="confirm_action_start",
                    session=session,
                    quick_actions=build_quick_actions(lang, "clarify", "confirm_action_start", session.get("last_scheme"), False),
                )
        else:
            session["action_confirmation_pending"] = True
            response_text = _action_start_confirmation_message(lang)
            _append_history(session, "assistant", response_text)
            update_session(session_id, session)
            return _build_response(
                session_id=session_id,
                response_text=response_text,
                field_name=None,
                validation_passed=True,
                validation_error=None,
                session_complete=False,
                mode="clarify",
                action="confirm_action_start",
                session=session,
                quick_actions=build_quick_actions(lang, "clarify", "confirm_action_start", session.get("last_scheme"), False),
            )

    # First-turn auto prompt: when session is new and form has not started.
    if not session.get("user_profile") and not session.get("conversation_history"):
        first_question = get_field_question(current_field, lang)
        _append_history(session, "assistant", first_question)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=first_question,
            field_name=current_field,
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            session=session,
            quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
        )

    if not cleaned_input or len(cleaned_input) < 2:
        retry_message = "कृपया स्पष्ट रूप से बताएं।" if lang == "hi" else "Please share your response clearly."
        _append_history(session, "assistant", retry_message)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=retry_message,
            field_name=current_field,
            validation_passed=False,
            validation_error="empty_or_too_short_input",
            session_complete=False,
            session=session,
            quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
        )

    if _is_restart_command(cleaned_input):
        _append_history(session, "user", cleaned_input)
        delete_session(session_id)
        session = create_session(session_id)
        session = _normalize_session_state(session)
        session["language"] = lang
        message = get_field_question(session.get("next_field"), lang)
        _append_history(session, "assistant", message)
        update_session(session_id, session)
        return _build_response(
            session_id,
            message,
            session.get("next_field"),
            True,
            False,
            None,
            session=session,
            quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
        )

    if _is_go_back_command(cleaned_input):
        _append_history(session, "user", cleaned_input)
        previous = _move_to_previous_field(session)
        question = get_field_question(previous, lang)
        session["session_complete"] = False
        _append_history(session, "assistant", question)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=question,
            field_name=session.get("next_field"),
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            session=session,
            quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
        )

    if _is_skip_command(cleaned_input):
        _append_history(session, "user", cleaned_input)
        if current_field:
            session.setdefault("field_completion", {})[current_field] = True
            session.setdefault("user_profile", {})[current_field] = None
            session["last_completed_field_index"] = LOAN_FIELDS.index(current_field)
        session["next_field"] = get_next_field(session)
        session["session_complete"] = False

        if session.get("next_field") is None:
            session["confirmation_state"] = "pending"
            confirmation_text = _build_confirmation_summary(session, lang)
            _append_history(session, "assistant", confirmation_text)
            update_session(session_id, session)
            return _build_response(
                session_id=session_id,
                response_text=confirmation_text,
                field_name=None,
                validation_passed=True,
                validation_error=None,
                session_complete=False,
                session=session,
                quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
            )

        question = get_field_question(session.get("next_field"), lang)
        _append_history(session, "assistant", question)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=question,
            field_name=session.get("next_field"),
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            session=session,
            quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
        )

    _append_history(session, "user", cleaned_input)

    if session.get("ocr_confirmation_pending", False):
        return _handle_ocr_confirmation(session_id, session, cleaned_input, lang)

    if session.get("confirmation_state") == "pending" and get_next_field(session) is None:
        return _confirmation_handler(session_id, session, cleaned_input, lang)

    if current_field and cleaned_input:
        if _is_ambiguous_input(cleaned_input):
            message = "कृपया सटीक मान बताएं।" if lang == "hi" else "Please provide the exact value."
            question = get_field_question(current_field, lang)
            merged = f"{message}. {question}"
            _append_history(session, "assistant", merged)
            update_session(session_id, session)
            return _build_response(
                session_id=session_id,
                response_text=merged,
                field_name=current_field,
                validation_passed=False,
                validation_error="ambiguous_input",
                session_complete=False,
                session=session,
                quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
            )

        agent_result = run_agent(session, cleaned_input, store_history=False)
        candidate_value = agent_result.get("field_value") or cleaned_input

        is_valid, normalized_value, error_message = validate(current_field, candidate_value)
        if not is_valid:
            retry_message = _validation_error_message(current_field, error_message or "invalid", lang)
            question = get_field_question(current_field, lang)
            merged_message = f"{retry_message}. {question}"
            _append_history(session, "assistant", merged_message)
            update_session(session_id, session)
            return _build_response(
                session_id=session_id,
                response_text=merged_message,
                field_name=current_field,
                validation_passed=False,
                validation_error=error_message,
                session_complete=False,
                session=session,
                quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
            )

        session.setdefault("user_profile", {})[current_field] = normalized_value
        session.setdefault("field_completion", {})[current_field] = True
        session["last_completed_field_index"] = LOAN_FIELDS.index(current_field)

    next_field = get_next_field(session)
    session["next_field"] = next_field
    session["session_complete"] = False

    if next_field is None:
        if not session.get("confirmation_done", False):
            session["confirmation_state"] = "pending"
            confirmation_text = _build_confirmation_summary(session, lang)
            _append_history(session, "assistant", confirmation_text)
            update_session(session_id, session)
            return _build_response(
                session_id=session_id,
                response_text=confirmation_text,
                field_name=None,
                validation_passed=True,
                validation_error=None,
                session_complete=False,
                session=session,
                quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
            )

        session["confirmation_state"] = "confirmed"
        session["session_complete"] = True
        completion_message = get_field_question(None, lang)
        _append_history(session, "assistant", completion_message)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=completion_message,
            field_name=None,
            validation_passed=True,
            validation_error=None,
            session_complete=True,
            session=session,
            quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), True),
        )

    prompt_result = run_agent(session, "")
    question = prompt_result.get("next_question_text") or get_field_question(session["next_field"], lang)

    update_session(session_id, session)

    return _build_response(
        session_id=session_id,
        response_text=question,
        field_name=session["next_field"],
        validation_passed=True,
        validation_error=None,
        session_complete=False,
        session=session,
        quick_actions=build_quick_actions(lang, "action", None, session.get("last_scheme"), False),
    )


class ConversationService:
    def process(self, session_id: str, user_input: str, language: Optional[str] = None, debug: bool = False) -> Dict[str, Any]:
        log_event("conversation_service_start", endpoint="conversation_service", status="success", user_input_length=len(user_input or ""))
        try:
            result = handle_conversation(session_id=session_id, user_input=user_input, language=language, debug=debug)
            # Enrich session with compact semantic memory for context-aware follow-up replies.
            session = get_session(session_id)
            _update_semantic_memory(session, user_input, result, result.get("primary_intent") or "")
            update_session(session_id, session)
            log_event("conversation_service_success", endpoint="conversation_service", status="success", intent=result.get("primary_intent"), confidence=(result.get("intent_debug") or {}).get("confidence"))
            return result
        except Exception as exc:
            log_event("conversation_service_failure", level="error", endpoint="conversation_service", status="failure", error_type=type(exc).__name__)
            raise

    def merge_ocr(self, session: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        log_event("conversation_service_merge_ocr_start", endpoint="conversation_service", status="success")
        try:
            result = merge_ocr_data(session, extracted_data)
            log_event("conversation_service_merge_ocr_success", endpoint="conversation_service", status="success")
            return result
        except Exception as exc:
            log_event("conversation_service_merge_ocr_failure", level="error", endpoint="conversation_service", status="failure", error_type=type(exc).__name__)
            raise

    def ocr_confirmation(self, session: Dict[str, Any], ocr_data: Dict[str, Any], language: str) -> str:
        log_event("conversation_service_ocr_confirmation_start", endpoint="conversation_service", status="success")
        try:
            result = get_ocr_confirmation_message(session, ocr_data, language)
            log_event("conversation_service_ocr_confirmation_success", endpoint="conversation_service", status="success")
            return result
        except Exception as exc:
            log_event("conversation_service_ocr_confirmation_failure", level="error", endpoint="conversation_service", status="failure", error_type=type(exc).__name__)
            raise
