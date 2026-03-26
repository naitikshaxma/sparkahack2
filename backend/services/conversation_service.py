import re
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ..bert_service import predict_intent_detailed
from ..intent_router import detect_intent_and_mode, is_followup_info_query
from ..intents import ACTION_INTENTS, INFO_INTENTS, INTENT_SCHEME_QUERY
from ..rag_service import recommend_schemes, recommend_schemes_with_reasons, retrieve_scheme_with_recommendations
from ..decision_engine import detect_user_need
from ..response_formatter import (
    build_quick_actions,
    build_recommendation_quick_actions,
    build_scheme_details,
    format_info_text,
    format_short_voice_text,
)
from ..metrics import record_fallback
from ..logger import log_event
from ..utils.language import normalize_language_code
from ..utils.privacy import redact_sensitive_text, sanitize_profile_for_response
from ..utils.context_fusion import adaptive_confidence_thresholds, build_context_fusion
from ..utils.form_schema import (
    get_default_scheme_for_category,
    get_field_question,
    get_fields_for_scheme,
    get_next_field,
    resolve_scheme_name,
    validate_field,
)
from ..utils.session_manager import create_session, delete_session, get_session, update_session
from ..utils.validator import validate
from ..text_normalizer import normalize_for_intent
from ..validators.input_validator import validate_input as security_validate_input
from .agent_service import run_agent
from .intent_service import IntentService


logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 10
MAX_SEMANTIC_MEMORY_ITEMS = 12
MAX_TEXT_INPUT_CHARS = max(64, int((os.getenv("MAX_TEXT_INPUT_CHARS") or "500").strip() or "500"))
AMBIGUOUS_WORDS = {"maybe", "around", "approx", "lagbhag", "approximately"}
YES_WORDS = {"yes", "ok", "okay", "haan", "ha", "haan ji", "ji", "theek hai", "ठीक है", "correct", "sahi", "right", "confirm", "confirmed"}
NO_WORDS = {"no", "nahin", "nahi", "galat", "wrong", "not correct", "cancel"}
UNCLEAR_WORDS = {"hmm", "uh", "hello", "helo", "sun", "listen", "something", "kuch", "pata nahi", "not sure"}
GENERIC_HELP_PATTERNS = {
    "loan batao",
    "loan",
    "scheme batao",
    "scheme",
    "madad chahiye",
    "help",
    "yojana",
    "help chahiye",
    "yojana batao",
    "koi scheme",
    "kuch scheme",
}

FIELD_LABELS = {
    "full_name": {"en": "Full Name", "hi": "पूरा नाम"},
    "phone": {"en": "Phone", "hi": "मोबाइल नंबर"},
    "aadhaar_number": {"en": "Aadhaar", "hi": "आधार नंबर"},
    "annual_income": {"en": "Annual Income", "hi": "वार्षिक आय"},
    "land_holding_acres": {"en": "Land Holding", "hi": "भूमि होल्डिंग"},
    "farmer_id": {"en": "Farmer ID", "hi": "किसान आईडी"},
    "health_card_number": {"en": "Health Card Number", "hi": "हेल्थ कार्ड नंबर"},
    "family_size": {"en": "Family Size", "hi": "परिवार का आकार"},
    "residential_status": {"en": "Residential Status", "hi": "आवासीय स्थिति"},
    "property_ownership": {"en": "Property Ownership", "hi": "संपत्ति स्वामित्व"},
}

SCHEME_ENTITY_RE = re.compile(r"\b(pm\s*kisan|ayushman|pmay|pension|loan)\b", re.IGNORECASE)
NUMBER_ENTITY_RE = re.compile(r"\b\d{4,}\b")
INTENT_SERVICE = IntentService()
DIALOGUE_STATES = {"idle", "collecting_info", "confirming", "completed"}
EXTRACTION_AUTO_FILL_THRESHOLD = 0.72
MAX_INVALID_ATTEMPTS_PER_FIELD = 3
CORRECTION_PATTERNS = {
    "wrong",
    "change",
    "update",
    "edit",
    "not correct",
    "गलत",
    "बदल",
    "सुधार",
}


def _session_fields(session: Dict[str, Any]) -> List[str]:
    return get_fields_for_scheme(session.get("selected_scheme"))


def _detect_user_type(text: str) -> Optional[str]:
    query = (text or "").strip().lower()
    if any(token in query for token in {"farmer", "kisan", "किसान"}):
        return "farmer"
    if any(token in query for token in {"student", "विद्यार्थी", "छात्र"}):
        return "student"
    if any(token in query for token in {"business", "shop", "व्यापार", "कारोबार"}):
        return "business"
    return None


def _detect_income_range(text: str) -> Optional[str]:
    query = (text or "").strip().lower()
    if any(token in query for token in {"below", "under", "less than", "कम", "below 2", "under 2"}):
        return "low"
    if any(token in query for token in {"between", "mid", "मध्यम"}):
        return "mid"
    if any(token in query for token in {"high", "above", "more than", "ज्यादा"}):
        return "high"
    return None


def _update_user_need_profile(session: Dict[str, Any], user_input: str, need_category: Optional[str] = None) -> Dict[str, Optional[str]]:
    profile = dict(session.get("user_need_profile", {}))
    detected_user_type = _detect_user_type(user_input)
    detected_income_range = _detect_income_range(user_input)

    if detected_user_type:
        profile["user_type"] = detected_user_type
    if detected_income_range:
        profile["income_range"] = detected_income_range
    if need_category:
        profile["need_category"] = need_category

    profile.setdefault("user_type", None)
    profile.setdefault("income_range", None)
    profile.setdefault("need_category", None)
    session["user_need_profile"] = profile
    return profile


def _session_feedback(session: Dict[str, Any]) -> Dict[str, object]:
    learning_profile = session.get("learning_profile") or {}
    return {
        "rejected_schemes": list(session.get("rejected_schemes", [])),
        "accepted_scheme": session.get("accepted_scheme"),
        "accepted_category": (session.get("user_need_profile") or {}).get("need_category"),
        "rejected_counts": dict(learning_profile.get("rejected_counts", {})),
        "accepted_counts": dict(learning_profile.get("accepted_counts", {})),
    }


def _maybe_update_feedback_from_input(session: Dict[str, Any], user_input: str) -> None:
    text = (user_input or "").strip().lower()
    last_scheme = str(session.get("last_scheme") or "").strip()
    if not last_scheme:
        return

    rejected_markers = {"not this", "nahi", "nahin", "no", "another", "different scheme"}
    if any(marker in text for marker in rejected_markers):
        rejected = set(session.get("rejected_schemes", []))
        rejected.add(last_scheme)
        session["rejected_schemes"] = sorted(rejected)
        learning = session.setdefault("learning_profile", {"rejected_counts": {}, "accepted_counts": {}})
        rejected_counts = learning.setdefault("rejected_counts", {})
        key = str(last_scheme).strip().lower()
        rejected_counts[key] = int(rejected_counts.get(key, 0)) + 1


def _mark_accepted_scheme(session: Dict[str, Any], scheme_name: str) -> None:
    selected = str(scheme_name or "").strip()
    if not selected:
        return
    session["accepted_scheme"] = selected
    learning = session.setdefault("learning_profile", {"rejected_counts": {}, "accepted_counts": {}})
    accepted_counts = learning.setdefault("accepted_counts", {})
    key = selected.lower()
    accepted_counts[key] = int(accepted_counts.get(key, 0)) + 1


def _summarize_history_messages(messages: List[Dict[str, str]]) -> str:
    snippets: List[str] = []
    for item in messages[-6:]:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        snippets.append(f"{role}:{content[:80]}")
    return " | ".join(snippets)[:400]


def _push_clarification(session: Dict[str, Any], context: str) -> None:
    stack = session.setdefault("clarification_stack", [])
    entry = (context or "").strip()
    if not entry:
        return
    stack.append(entry)
    session["clarification_stack"] = stack[-5:]


def _pop_clarification(session: Dict[str, Any]) -> str:
    stack = session.setdefault("clarification_stack", [])
    if not stack:
        return ""
    context = str(stack.pop() or "").strip()
    session["clarification_stack"] = stack
    return context


def _safe_reset_session(session_id: str, language: str) -> Dict[str, Any]:
    delete_session(session_id)
    fresh = create_session(session_id)
    fresh = _normalize_session_state(fresh)
    fresh["language"] = language
    fresh["dialogue_state"] = "collecting_info"
    return fresh


def _trim_history(session: Dict[str, Any]) -> None:
    history = session.setdefault("conversation_history", [])
    if len(history) > MAX_HISTORY_MESSAGES:
        overflow = history[:-MAX_HISTORY_MESSAGES]
        existing_summary = str(session.get("history_summary") or "").strip()
        delta_summary = _summarize_history_messages(overflow)
        if delta_summary:
            session["history_summary"] = (f"{existing_summary} | {delta_summary}" if existing_summary else delta_summary)[:800]
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
    active_fields = _session_fields(session or {}) if session else get_fields_for_scheme(None)
    steps_total = len(active_fields)
    if session:
        completion = session.get("field_completion", {})
        steps_done = sum(1 for field in active_fields if completion.get(field))

    language = normalize_language_code((session or {}).get("language", "en") if session else "en", default="en")
    completed_fields = []
    if session:
        completion = session.get("field_completion", {})
        for field in active_fields:
            if completion.get(field):
                completed_fields.append(FIELD_LABELS.get(field, {}).get(language, field))

    natural_response = format_response(response_text, language)
    natural_voice = format_response(voice_text or natural_response, language)
    synced_display = _display_aligned_text(natural_response, language)
    base_quick_actions = list(quick_actions or [])
    merged_actions = _merge_control_actions(language, base_quick_actions)

    return {
        "session_id": session_id,
        "response_text": synced_display,
        "voice_text": natural_voice or format_short_voice_text(natural_response, language),
        "instant_ack": _micro_latency_ack(language),
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
        "quick_actions": merged_actions,
        "recommended_schemes": recommended_schemes or [],
        "user_profile": sanitize_profile_for_response((session or {}).get("user_profile", {})),
        "intent_debug": (session or {}).get("_intent_debug"),
    }


def format_response(text: str, language: str) -> str:
    content = str(text or "").strip()
    if not content:
        return content

    if language == "hi":
        replacements = {
            "कृपया बताएं": "बताइए",
            "कृपया": "ज़रा",
            "क्या आप": "आप",
            "मैं आपकी मदद कर सकता हूँ": "मैं आपकी पूरी मदद करूँगा",
            "क्या यह सही है": "ये ठीक है ना",
        }
        for source, target in replacements.items():
            content = content.replace(source, target)
    else:
        replacements = {
            "Please provide": "Share",
            "Please tell me": "Tell me",
            "I can help with this.": "I can help with that.",
            "Do you want": "Would you like",
        }
        for source, target in replacements.items():
            content = content.replace(source, target)

    # Smooth punctuation keeps replies sounding less robotic.
    content = re.sub(r"\s+", " ", content).strip()
    content = content.replace("..", ".")
    return content


def _normalize_mixed_input_text(user_input: str) -> str:
    text = str(user_input or "").strip()
    if not text:
        return ""
    text = text.replace("।", ".")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_affirmative(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    if text in YES_WORDS:
        return True
    markers = {"yes", "ok", "okay", "haan", "theek", "ठीक", "confirm", "sahi"}
    return any(marker in text for marker in markers)


def _is_negative(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    if text in NO_WORDS:
        return True
    markers = {"no", "nah", "nahi", "nahin", "गलत", "wrong", "cancel"}
    return any(marker in text for marker in markers)


def _micro_latency_ack(language: str) -> str:
    return "ठीक है, एक पल..." if language == "hi" else "Got it, just a moment..."


def _merge_control_actions(language: str, quick_actions: List[Dict[str, str]]) -> List[Dict[str, str]]:
    controls = [
        {
            "label": "जारी रखें" if language == "hi" else "Continue",
            "value": "continue_flow",
        },
        {
            "label": "सुझाव बदलें" if language == "hi" else "Refine",
            "value": "refine_suggestions",
        },
        {
            "label": "अभी आवेदन करें" if language == "hi" else "Apply",
            "value": "apply_now_direct",
        },
    ]
    seen = set()
    merged: List[Dict[str, str]] = []
    for action in [*quick_actions, *controls]:
        value = str(action.get("value") or "").strip()
        label = str(action.get("label") or "").strip()
        if not value or not label or value in seen:
            continue
        seen.add(value)
        merged.append({"label": label, "value": value})
    return merged


def _is_short_query(text: str) -> bool:
    tokens = [token for token in (text or "").strip().split() if token]
    return len(tokens) <= 4


def _display_aligned_text(text: str, language: str) -> str:
    words = [token for token in (text or "").replace("\n", " ").split() if token]
    if len(words) <= 34:
        return text
    lead = " ".join(words[:30]).rstrip(".,;: ")
    return f"{lead}..." if language == "en" else f"{lead}..."


def _short_answer(text: str, language: str) -> str:
    words = [token for token in (text or "").replace("\n", " ").split() if token]
    if len(words) <= 18:
        return text
    concise = " ".join(words[:16]).rstrip(".,;: ")
    return f"{concise}..." if language == "en" else f"{concise}..."


def _recommendation_confirmation_prompt(language: str) -> str:
    if language == "hi":
        return "क्या ये सुझाव सही लग रहे हैं, या मैं इन्हें और बेहतर करके दिखाऊँ?"
    return "Do these suggestions look right, or should I refine them further?"


def _confidence_explanation_line(language: str, reason: str) -> str:
    detail = (reason or "").strip()
    if language == "hi":
        return f"मैंने ये सुझाव आपकी बात और प्रोफ़ाइल के आधार पर दिए हैं। {detail}".strip()
    return f"I suggested this based on your request and profile context. {detail}".strip()


def _closing_summary(session: Dict[str, Any], language: str) -> str:
    scheme = str(session.get("last_scheme") or session.get("accepted_scheme") or "").strip()
    if language == "hi":
        if scheme:
            return f"आज हमने {scheme} पर आपकी मदद पूरी की। अगर चाहें तो अगले कदम में भी मैं साथ हूँ।"
        return "आज की प्रक्रिया आराम से पूरी हो गई। अगर चाहें तो मैं आगे भी मदद के लिए हूँ।"
    if scheme:
        return f"We completed {scheme} together. I can help you with the next step too."
    return "We completed this step smoothly. I am here if you need anything else."


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
        "continue_flow": "next",
        "refine_suggestions": "different scheme",
        "apply_now_direct": "start application",
        "restart_session": "restart",
        "auto_fill_form": "auto fill form",
    }
    return mapping.get(lowered, raw)


def _reset_session_state(session: Dict[str, Any]) -> Dict[str, Any]:
    # Kept for compatibility, but hard reset now uses delete + create.
    selected_scheme = resolve_scheme_name(session.get("selected_scheme") or session.get("last_scheme"))
    dynamic_fields = get_fields_for_scheme(selected_scheme)
    field_completion = {field: False for field in dynamic_fields}
    session["selected_scheme"] = selected_scheme
    session["user_profile"] = {}
    session["field_completion"] = field_completion
    session["next_field"] = dynamic_fields[0] if dynamic_fields else None
    session["session_complete"] = False
    session["conversation_history"] = []
    session["last_completed_field_index"] = -1
    session["confirmation_done"] = False
    session["confirmation_state"] = "pending"
    return session


def _normalize_session_state(session: Dict[str, Any]) -> Dict[str, Any]:
    # Protect against corrupted or partially missing session payloads.
    selected_scheme = resolve_scheme_name(session.get("selected_scheme") or session.get("last_scheme"))
    session["selected_scheme"] = selected_scheme
    dynamic_fields = get_fields_for_scheme(selected_scheme)

    session.setdefault("user_profile", {})
    session.setdefault("field_completion", {field: False for field in dynamic_fields})
    session["field_completion"] = {
        field: bool(session.get("field_completion", {}).get(field, False))
        for field in dynamic_fields
    }

    session.setdefault("conversation_history", [])
    session.setdefault("session_complete", False)
    session.setdefault("confirmation_done", False)
    session.setdefault("confirmation_state", "pending")
    session.setdefault("last_completed_field_index", -1)
    session.setdefault("ocr_extracted", {"fields": [], "confidence": 0.0})
    session.setdefault("ocr_confirmation_pending", False)
    session.setdefault("ocr_pending_fields", [])
    session.setdefault("action_confirmation_pending", False)
    session.setdefault("user_need_profile", {"user_type": None, "income_range": None, "need_category": None})
    session.setdefault("history_summary", "")
    session.setdefault("past_need_confidence", None)
    session.setdefault("onboarding_done", False)
    session.setdefault("rejected_schemes", [])
    session.setdefault("accepted_scheme", None)
    session.setdefault("last_recommendation_reason", None)
    session.setdefault("learning_profile", {"rejected_counts": {}, "accepted_counts": {}})
    session.setdefault("dialogue_state", "idle")
    session.setdefault("clarification_pending", False)
    session.setdefault("clarification_context", "")
    session.setdefault("clarification_stack", [])
    session.setdefault("invalid_attempts", {})
    session.setdefault("extraction_conflicts", {})

    next_field = session.get("next_field")
    if next_field not in dynamic_fields and next_field is not None:
        next_field = get_next_field(session)
    if next_field is None and not session.get("session_complete", False):
        next_field = get_next_field(session)
    session["next_field"] = next_field
    return session


def _update_dialogue_state(session: Dict[str, Any]) -> str:
    current = str(session.get("dialogue_state") or "idle").strip().lower()
    if current not in DIALOGUE_STATES:
        current = "idle"

    next_field = get_next_field(session)
    confirmation_state = str(session.get("confirmation_state") or "pending").strip().lower()

    if session.get("session_complete") or confirmation_state == "confirmed":
        current = "completed"
    elif confirmation_state == "pending" and next_field is None:
        current = "confirming"
    elif next_field is not None:
        current = "collecting_info"
    else:
        current = "idle"

    session["dialogue_state"] = current
    return current


def _is_correction_request(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in CORRECTION_PATTERNS)


def _unique_candidates(candidates: List[Tuple[str, float]]) -> List[Dict[str, Any]]:
    seen: Dict[str, float] = {}
    for value, conf in candidates:
        key = str(value or "").strip()
        if not key:
            continue
        seen[key] = max(float(conf), seen.get(key, 0.0))
    return [{"value": key, "confidence": round(score, 3)} for key, score in seen.items()]


def _extract_multi_field_values(text: str) -> Dict[str, List[Dict[str, Any]]]:
    content = (text or "").strip()
    lowered = content.lower()
    extracted: Dict[str, List[Dict[str, Any]]] = {}

    phones = re.findall(r"(?<!\d)(\d{10})(?!\d)", content)
    if phones:
        phone_conf = 0.94 if len(set(phones)) == 1 else 0.76
        extracted["phone"] = _unique_candidates([(value, phone_conf) for value in phones])

    aadhaars = re.findall(r"(?<!\d)(\d{12})(?!\d)", content)
    if aadhaars:
        aadhaar_conf = 0.96 if len(set(aadhaars)) == 1 else 0.74
        extracted["aadhaar_number"] = _unique_candidates([(value, aadhaar_conf) for value in aadhaars])

    incomes = re.findall(r"(?:income|आय|salary|कमाई)\D{0,12}(\d+(?:,\d{3})*(?:\.\d+)?)", lowered)
    if incomes:
        extracted["annual_income"] = _unique_candidates([(value.replace(",", ""), 0.86) for value in incomes])

    name_match = re.search(r"(?:my name is|i am|name[:\s]|मेरा नाम|नाम)\s*[:\-]?\s*([A-Za-z\u0900-\u097F\s.'-]{2,80})", content, re.IGNORECASE)
    if name_match:
        extracted["full_name"] = _unique_candidates([(name_match.group(1).strip(), 0.84)])

    return extracted


def _apply_extracted_fields(session: Dict[str, Any], extracted: Dict[str, List[Dict[str, Any]]], language: str) -> Dict[str, Any]:
    active_fields = _session_fields(session)
    completion = session.setdefault("field_completion", {})
    profile = session.setdefault("user_profile", {})
    applied: Dict[str, str] = {}
    errors: Dict[str, str] = {}
    conflicts: Dict[str, List[str]] = {}
    low_confidence: Dict[str, float] = {}

    for field, candidates in extracted.items():
        if field not in active_fields or completion.get(field):
            continue

        values = [str(item.get("value") or "").strip() for item in candidates if str(item.get("value") or "").strip()]
        if len(set(values)) > 1:
            conflicts[field] = sorted(set(values))[:4]
            continue

        if not candidates:
            continue

        best = max(candidates, key=lambda item: float(item.get("confidence") or 0.0))
        best_value = str(best.get("value") or "").strip()
        best_confidence = float(best.get("confidence") or 0.0)

        if best_confidence < EXTRACTION_AUTO_FILL_THRESHOLD:
            low_confidence[field] = best_confidence
            continue

        result = validate_field(field, best_value, language=language)
        if result.get("valid"):
            profile[field] = str(result.get("normalized") or "")
            completion[field] = True
            applied[field] = str(result.get("normalized") or "")
        else:
            errors[field] = str(result.get("error_message") or "")

    if applied:
        last_field = None
        for field in active_fields:
            if completion.get(field):
                last_field = field
        if last_field in active_fields:
            session["last_completed_field_index"] = active_fields.index(last_field)

    return {
        "applied": applied,
        "errors": errors,
        "conflicts": conflicts,
        "low_confidence": low_confidence,
    }


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
        active_fields = _session_fields(session)
        session["last_completed_field_index"] = max(active_fields.index(f) for f in updated_fields if f in active_fields)

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
    cleaned_input = _normalize_mixed_input_text(user_input).lower()

    if _is_affirmative(cleaned_input):
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

    if _is_negative(cleaned_input) or _is_go_back_command(cleaned_input) or "correct" in cleaned_input:
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


def _is_generic_help_query(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    if len(text.split()) <= 2 and text in {"loan", "scheme", "help", "yojana", "madad"}:
        return True
    if text in GENERIC_HELP_PATTERNS:
        return True
    return any(pattern in text for pattern in GENERIC_HELP_PATTERNS)


def _recommendation_suffix(language: str, recommendations: List[str]) -> str:
    if not recommendations:
        return ""
    if language == "hi":
        return f"\n\nआप इन योजनाओं के बारे में पूछ सकते हैं: {', '.join(recommendations)}"
    return f"\n\nYou can ask about these schemes: {', '.join(recommendations)}"


def _guided_followup_question(user_input: str, language: str) -> str:
    query = (user_input or "").strip().lower()
    if any(token in query for token in {"loan", "credit", "finance", "financial", "लोन", "ऋण"}):
        if language == "hi":
            return "आपको किस तरह का लोन चाहिए: किसान, छात्र, या छोटे बिज़नेस के लिए?"
        return "Which type of loan do you need: farmer, student, or small business?"
    if any(token in query for token in {"health", "hospital", "medical", "स्वास्थ्य", "इलाज"}):
        if language == "hi":
            return "क्या मदद अस्पताल खर्च, बीमा, या परिवार कवरेज के लिए चाहिए?"
        return "Do you need help with hospital costs, insurance, or family coverage?"
    if any(token in query for token in {"house", "home", "housing", "घर", "आवास"}):
        if language == "hi":
            return "आपका फोकस घर खरीदना है, घर बनाना है, या किराए से राहत चाहिए?"
        return "Is your focus buying a house, building one, or rental support?"
    return (
        "मैं सही योजना चुनने के लिए एक बात जानना चाहूँगा: आपको तुरंत किस चीज़ में मदद चाहिए?"
        if language == "hi"
        else "To pick the best scheme, what is your top priority right now?"
    )


def _smart_clarification_message(language: str, recommendations: List[str], user_input: str = "") -> str:
    base = _guided_followup_question(user_input, language)
    return f"{base}{_recommendation_suffix(language, recommendations)}"


def _adaptive_recommendation_limit(confidence: float, low_threshold: float, high_threshold: float) -> int:
    if confidence > high_threshold:
        return 1
    if confidence < low_threshold:
        return 3
    return 2


def _apply_recommendation_continuity(session: Dict[str, Any], recommendations: List[str]) -> List[str]:
    previous = [str(item) for item in session.get("last_recommendations", []) if str(item).strip()]
    filtered = [item for item in recommendations if item not in previous]
    final_list = filtered or recommendations[:1]
    session["last_recommendations"] = final_list[:3]
    return final_list


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
    active_fields = _session_fields(session)
    parts: List[str] = []
    for field in active_fields:
        label = FIELD_LABELS.get(field, {}).get(language, field)
        value = profile.get(field)
        parts.append(f"{label}: {value if value not in {None, ''} else '-'}")

    joined = ", ".join(parts)

    if language == "hi":
        return f"मैं पुष्टि करता हूँ: {joined}. क्या यह सही है?"
    return f"Let me confirm: {joined}. Is this correct?"


def _move_to_previous_field(session: Dict[str, Any]) -> Optional[str]:
    last_index = int(session.get("last_completed_field_index", -1))
    active_fields = _session_fields(session)
    if last_index < 0:
        return session.get("next_field")
    if last_index >= len(active_fields):
        last_index = len(active_fields) - 1
    if last_index < 0:
        return session.get("next_field")

    previous_field = active_fields[last_index]
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
    cleaned_input = _normalize_mixed_input_text(user_input).lower()

    if _is_restart_command(cleaned_input):
        fresh = _safe_reset_session(session_id, language)
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

    if _is_affirmative(cleaned_input):
        session["confirmation_done"] = True
        session["confirmation_state"] = "confirmed"
        session["session_complete"] = True
        done_text = (
            "धन्यवाद, आपका फॉर्म पुष्टि हो गया है।"
            if language == "hi"
            else "Thank you, your form is confirmed."
        )
        done_text = f"{done_text}\n\n{_closing_summary(session, language)}"
        _append_history(session, "assistant", done_text)
        update_session(session_id, session)
        return _build_response(session_id, done_text, None, True, True, None, session=session)

    if _is_negative(cleaned_input):
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
    if field == "phone":
        return (
            "मोबाइल नंबर सही नहीं है। उदाहरण: 9876543210"
            if language == "hi"
            else "That mobile number looks invalid. Example: 9876543210"
        )
    if field == "aadhaar_number":
        return (
            "आधार नंबर सही नहीं है। उदाहरण: 123412341234"
            if language == "hi"
            else "That Aadhaar number looks invalid. Example: 123412341234"
        )
    if field == "annual_income":
        return (
            "आय सिर्फ अंकों में बताएं। उदाहरण: 250000"
            if language == "hi"
            else "Please share income in numbers only. Example: 250000"
        )
    if language == "hi":
        return "इनपुट अमान्य है, कृपया दोबारा बताएं।"
    return "Invalid input. Please try again."


def _clarification_message(language: str) -> str:
    if language == "hi":
        return "आप चाहें तो पहले योजना समझ लेते हैं, या अभी आवेदन शुरू कर सकते हैं।"
    return "We can first review the scheme details, or start your application right away."


def _action_start_confirmation_message(language: str) -> str:
    if language == "hi":
        return "मैं आवेदन फॉर्म शुरू कर दूँ? बस हाँ या नहीं कह दीजिए।"
    return "Shall I start your application form now? Just say yes or no."
    
def _resolve_extraction_conflicts(session: Dict[str, Any], user_input: str, language: str) -> bool:
    conflicts = dict(session.get("extraction_conflicts") or {})
    if not conflicts:
        return False

    field = next(iter(conflicts.keys()))
    options = [str(v).strip() for v in conflicts.get(field, []) if str(v).strip()]
    text = (user_input or "").strip()
    selected = None

    ordinal_map = {
        "first": 0,
        "1st": 0,
        "पहला": 0,
        "pehla": 0,
        "second": 1,
        "2nd": 1,
        "दूसरा": 1,
        "dusra": 1,
        "third": 2,
        "3rd": 2,
        "तीसरा": 2,
        "teesra": 2,
    }

    number_match = re.search(r"\b([1-9])\b", text)
    if number_match:
        idx = int(number_match.group(1)) - 1
        if 0 <= idx < len(options):
            selected = options[idx]

    lowered_text = text.lower()
    if selected is None:
        for token, idx in ordinal_map.items():
            if token in lowered_text and 0 <= idx < len(options):
                selected = options[idx]
                break

    if not selected:
        for option in options:
            if option and option in text:
                selected = option
                break

    # Correction override: "not this, use that" prefers latest explicit value.
    override_match = re.search(r"(?:not this|गलत|nahi)\s*,?\s*(?:use|choose|select|lo|ले)\s+(.+)$", lowered_text)
    if override_match and options:
        tail = override_match.group(1).strip()
        for option in options:
            if option.lower() in tail:
                selected = option
                break
        if selected is None:
            selected = options[-1]

    if not selected:
        option_text = "; ".join(f"{i + 1}. {value}" for i, value in enumerate(options))
        prompt = (
            f"मुझे {FIELD_LABELS.get(field, {}).get('hi', field)} के लिए कई मान मिले। सही विकल्प चुनें: {option_text}"
            if language == "hi"
            else f"I found multiple values for {FIELD_LABELS.get(field, {}).get('en', field)}. Please choose: {option_text}"
        )
        session["pending_conflict_prompt"] = prompt
        return False

    validated = validate_field(field, selected, language=language)
    if not validated.get("valid"):
        return False

    session.setdefault("user_profile", {})[field] = str(validated.get("normalized") or "")
    session.setdefault("field_completion", {})[field] = True
    conflicts.pop(field, None)
    session["extraction_conflicts"] = conflicts
    session.pop("pending_conflict_prompt", None)
    return True


def handle_conversation(session_id: str, user_input: str, language: Optional[str] = None, debug: bool = False) -> Dict[str, Any]:
    try:
        session = get_session(session_id)
    except Exception:
        session = create_session(session_id)

    session = _normalize_session_state(session)

    validated_input = security_validate_input(user_input or "", max_chars=MAX_TEXT_INPUT_CHARS)
    if not validated_input.is_valid:
        raise ValueError(validated_input.rejected_reason or "Invalid user input.")

    # Use normalized text to avoid double escaping when upstream routes already sanitize payloads.
    cleaned_input = _normalize_mixed_input_text(validated_input.normalized_text)
    _update_dialogue_state(session)

    # Cold-start onboarding for first interaction in a new session.
    if not session.get("onboarding_done") and not session.get("conversation_history"):
        lang_probe = normalize_language_code(language or session.get("language") or _detect_language(cleaned_input), default="en")
        onboarding = "आपको किस तरह की मदद चाहिए?" if lang_probe == "hi" else "What kind of help do you need?"
        session["language"] = lang_probe
        session["onboarding_done"] = True
        _append_history(session, "assistant", onboarding)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=onboarding,
            field_name=None,
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            mode="clarify",
            action="onboarding",
            session=session,
            quick_actions=build_quick_actions(lang_probe, "clarify", "onboarding", session.get("last_scheme"), False),
            voice_text=onboarding,
        )

    _maybe_update_feedback_from_input(session, cleaned_input)
    normalized_input = normalize_for_intent(cleaned_input, language_hint=language or session.get("language"))
    if language and language.strip():
        session["language"] = normalize_language_code(language, default="en")
    elif session.get("language"):
        session["language"] = normalize_language_code(session.get("language"), default="en")
    else:
        session["language"] = normalize_language_code(normalized_input.language or _detect_language(cleaned_input), default="en")

    current_field = session.get("next_field") or get_next_field(session)
    session["next_field"] = current_field
    lang = normalize_language_code(session.get("language", "en"), default="en")
    session["language"] = lang
    cleaned_input = _resolve_quick_action_input(cleaned_input, lang, session)

    if _is_restart_command(cleaned_input):
        _append_history(session, "user", cleaned_input)
        session = _safe_reset_session(session_id, lang)
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

    if session.get("extraction_conflicts"):
        if not _resolve_extraction_conflicts(session, cleaned_input, lang):
            prompt = str(session.get("pending_conflict_prompt") or "")
            if prompt:
                _append_history(session, "assistant", prompt)
                update_session(session_id, session)
                return _build_response(
                    session_id=session_id,
                    response_text=prompt,
                    field_name=session.get("next_field") or get_next_field(session),
                    validation_passed=False,
                    validation_error="extraction_conflict",
                    session_complete=False,
                    mode="clarify",
                    action="resolve_extraction_conflict",
                    session=session,
                    quick_actions=build_quick_actions(lang, "clarify", "resolve_extraction_conflict", session.get("last_scheme"), False),
                )

    if _is_correction_request(cleaned_input) and _update_dialogue_state(session) in {"collecting_info", "confirming"}:
        previous = _move_to_previous_field(session)
        session["dialogue_state"] = "collecting_info"
        correction_prompt = get_field_question(previous, lang)
        _append_history(session, "assistant", correction_prompt)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=correction_prompt,
            field_name=previous,
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            mode="action",
            action="correction",
            session=session,
            quick_actions=build_quick_actions(lang, "action", "correction", session.get("last_scheme"), False),
        )

    normalized_input = normalize_for_intent(cleaned_input, language_hint=lang)

    # Clarification resume path: enrich terse follow-up using stack context.
    if session.get("clarification_stack") and len((normalized_input.intent_text or cleaned_input).split()) <= 5:
        previous_context = _pop_clarification(session)
        merged_text = f"{previous_context} {normalized_input.intent_text or cleaned_input}".strip()
        normalized_input = normalize_for_intent(merged_text, language_hint=lang)
    need_signal = detect_user_need(
        normalized_input.intent_text or cleaned_input,
        session_context={
            "user_need_profile": session.get("user_need_profile"),
            "conversation_history": session.get("conversation_history", []),
            "last_intent": session.get("last_intent"),
            "history_summary": session.get("history_summary"),
        },
    )
    need_category = str(need_signal.get("category") or "")
    need_confidence = float(need_signal.get("confidence") or 0.0)
    user_need_profile = _update_user_need_profile(session, cleaned_input, need_category=need_category)
    progress_started = any(session.get("field_completion", {}).get(field, False) for field in _session_fields(session))
    intent_debug = INTENT_SERVICE.detect(normalized_input.intent_text or cleaned_input, debug=True)
    intent_decision = predict_intent_detailed(
        normalized_input.intent_text or cleaned_input,
        session_context={
            "last_intent": session.get("last_intent"),
            "last_action": session.get("last_action"),
            "language": lang,
        },
    )
    intent_decision["primary_intent"] = intent_debug.get("intent", intent_decision.get("primary_intent"))
    intent_decision["confidence"] = round(float(intent_debug.get("confidence", 0.0)) / 100.0, 4)
    intent_decision["hybrid_debug"] = intent_debug.get("debug", {})
    model_intent = intent_decision["primary_intent"]
    model_confidence = float(intent_decision["confidence"])
    model_fallback_used = bool(intent_decision["fallback_used"])
    secondary_intents = intent_decision.get("secondary_intents", [])

    detected_intent, detected_mode = detect_intent_and_mode(
        normalized_input.intent_text or cleaned_input,
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
    conversational_intent = str((intent_debug.get("debug") or {}).get("conversation_intent") or "")
    conversational_confidence = float((intent_debug.get("debug") or {}).get("conversation_confidence") or 0.0)
    if conversational_intent == "correction":
        mode = "action"
    if conversational_confidence and conversational_confidence < 0.42:
        mode = "clarify"

    session["last_intent"] = model_intent
    session["last_secondary_intents"] = secondary_intents
    session["last_action"] = mode
    if debug:
        session["_intent_debug"] = intent_decision
    else:
        session.pop("_intent_debug", None)

    log_event(
        "conversation_routing_decision",
        endpoint="conversation_service",
        status="success",
        session_id=session_id,
        user_input=(normalized_input.intent_text or cleaned_input)[:220],
        detected_intent=detected_intent,
        model_intent=model_intent,
        confidence=round(model_confidence, 4),
        selected_scheme=session.get("selected_scheme"),
        fallback_used=model_fallback_used,
        secondary_intents=secondary_intents,
        selected_mode=mode,
        current_field=current_field,
        progress_started=progress_started,
    )

    fused_context = build_context_fusion(
        current_intent=model_intent,
        previous_intent=session.get("memory_last_intent"),
        user_profile={**(session.get("user_profile") or {}), **(session.get("user_need_profile") or {})},
        need_category=need_category,
        history_summary=session.get("history_summary"),
    )
    thresholds = adaptive_confidence_thresholds(
        query=normalized_input.intent_text or cleaned_input,
        past_confidence=session.get("past_need_confidence"),
        intent_type=model_intent,
    )
    low_threshold = float(thresholds.get("low", 0.6))
    high_threshold = float(thresholds.get("high", 0.8))
    recommendation_limit = _adaptive_recommendation_limit(need_confidence, low_threshold, high_threshold)
    short_mode = _is_short_query(normalized_input.intent_text or cleaned_input)
    session["past_need_confidence"] = need_confidence

    if cleaned_input.lower() in {"auto fill form", "autofill", "auto-fill"}:
        if session.get("session_complete"):
            auto_msg = (
                "बहुत बढ़िया, आपकी जानकारी पूरी है। अब Auto-fill चलाइए, मैं फॉर्म अपने-आप भरवा दूँगा।"
                if lang == "hi"
                else "Great, your details are complete. Run Auto-fill now and I will help prefill the form."
            )
            _append_history(session, "assistant", auto_msg)
            update_session(session_id, session)
            return _build_response(
                session_id=session_id,
                response_text=auto_msg,
                field_name=None,
                validation_passed=True,
                validation_error=None,
                session_complete=True,
                mode="action",
                action="auto_fill_form",
                session=session,
                quick_actions=build_quick_actions(lang, "action", "auto_fill_form", session.get("last_scheme"), True),
                voice_text=auto_msg,
            )
        auto_msg = (
            "Auto-fill शुरू करने से पहले 1-2 जानकारी और चाहिए। चलिए, उसे पूरा करते हैं।"
            if lang == "hi"
            else "Before auto-fill, I need 1-2 more details. Let us finish those first."
        )
        _append_history(session, "assistant", auto_msg)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=auto_msg,
            field_name=current_field,
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            mode="action",
            action="continue_form",
            session=session,
            quick_actions=build_quick_actions(lang, "action", "continue_form", session.get("last_scheme"), False),
            voice_text=auto_msg,
        )

    if cleaned_input.lower() in {"autofill completed", "autofill success", "auto fill done"}:
        success_msg = (
            "शानदार, फॉर्म सफलतापूर्वक भर गया। अब एक बार जानकारी देखकर submit कर दीजिए।"
            if lang == "hi"
            else "Perfect, your form has been filled successfully. Please review once and submit."
        )
        _append_history(session, "assistant", success_msg)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=success_msg,
            field_name=None,
            validation_passed=True,
            validation_error=None,
            session_complete=bool(session.get("session_complete")),
            mode="action",
            action="autofill_success",
            session=session,
            quick_actions=build_quick_actions(lang, "action", "autofill_success", session.get("last_scheme"), True),
            voice_text=success_msg,
        )

    if cleaned_input.lower() in {"autofill failed", "auto fill failed", "autofill error"}:
        failure_msg = (
            "कोई बात नहीं, कभी-कभी ऑटो-फिल में दिक्कत आती है। मैं step-by-step आपके साथ manually भरवा देता हूँ।"
            if lang == "hi"
            else "No worries, auto-fill can fail sometimes. I can guide you step-by-step to fill it manually."
        )
        recovery = get_field_question(session.get("next_field") or get_next_field(session), lang)
        merged_msg = f"{failure_msg} {recovery}".strip()
        _append_history(session, "assistant", merged_msg)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=merged_msg,
            field_name=session.get("next_field") or get_next_field(session),
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            mode="action",
            action="autofill_recovery",
            session=session,
            quick_actions=build_quick_actions(lang, "action", "autofill_recovery", session.get("last_scheme"), False),
            voice_text=merged_msg,
        )

    if _is_unclear_input(cleaned_input) or _is_generic_help_query(normalized_input.intent_text or cleaned_input):
        _push_clarification(session, normalized_input.intent_text or cleaned_input)
        record_fallback()
        recommendations = recommend_schemes(
            normalized_input.intent_text or cleaned_input,
            lang,
            limit=recommendation_limit,
            need_category=need_category,
            user_profile=user_need_profile,
            session_feedback=_session_feedback(session),
            context_fusion=fused_context,
        )
        explainable = recommend_schemes_with_reasons(
            normalized_input.intent_text or cleaned_input,
            lang,
            limit=recommendation_limit,
            need_category=need_category,
            user_profile=user_need_profile,
            session_feedback=_session_feedback(session),
            context_fusion=fused_context,
        )
        recommendations = _apply_recommendation_continuity(session, recommendations)
        need_prefix = (
            "आपकी ज़रूरत के आधार पर, ये योजनाएँ मदद कर सकती हैं।"
            if lang == "hi"
            else "Based on your need, these schemes may help."
        )
        reason_lines = "\n".join(f"- {item['scheme']}: {item['reason']}" for item in explainable)
        confidence_line = (
            "मुझे आपकी जरूरत समझने के लिए थोड़ी और जानकारी चाहिए।"
            if need_confidence < low_threshold and lang == "hi"
            else "I need one more detail to understand your need better."
            if need_confidence < low_threshold
            else ""
        )
        unclear_text = f"{need_prefix}\n{_smart_clarification_message(lang, recommendations, cleaned_input)}"
        if confidence_line:
            unclear_text = f"{unclear_text}\n\n{confidence_line}"
        if reason_lines:
            unclear_text = f"{unclear_text}\n\n{reason_lines}"
        unclear_text = f"{unclear_text}\n\n{_recommendation_confirmation_prompt(lang)}"
        _append_history(session, "user", cleaned_input)
        _append_history(session, "assistant", unclear_text)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=unclear_text,
            field_name=None,
            validation_passed=True,
            validation_error=None,
            session_complete=False,
            mode="clarify",
            action="clarify_intent",
            session=session,
            quick_actions=build_recommendation_quick_actions(recommendations, lang),
            recommended_schemes=recommendations,
            voice_text=unclear_text,
        )

    if mode == "clarify":
        _push_clarification(session, normalized_input.intent_text or cleaned_input)
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

        rag_response, recommendations, has_match = retrieve_scheme_with_recommendations(
            transcript=query_for_rag,
            language=lang,
            limit=recommendation_limit,
            need_category=need_category,
            user_profile=user_need_profile,
            session_feedback=_session_feedback(session),
            context_fusion=fused_context,
        )
        explainable = recommend_schemes_with_reasons(
            query_for_rag,
            language=lang,
            limit=recommendation_limit,
            need_category=need_category,
            user_profile=user_need_profile,
            session_feedback=_session_feedback(session),
            context_fusion=fused_context,
        )
        recommendations = _apply_recommendation_continuity(session, recommendations)

        if rag_response is None:
            rag_response = {
                "confirmation": (
                    "मैं आपकी बात समझ गया। मैं सही योजना चुनने में मदद कर सकता हूँ।"
                    if lang == "hi"
                    else "I understood your request. I can help you pick the right scheme."
                ),
                "explanation": (
                    "कृपया बताएं कि आपको किसान, स्वास्थ्य, आवास, पेंशन या छात्रवृत्ति में से किस तरह की मदद चाहिए।"
                    if lang == "hi"
                    else "Please tell me whether you need help with farmer, health, housing, pension, or scholarship schemes."
                ),
                "next_step": (
                    "आप पात्रता, दस्तावेज़, लाभ या आवेदन प्रक्रिया में से कुछ भी पूछ सकते हैं।"
                    if lang == "hi"
                    else "You can ask for eligibility, documents, benefits, or application process."
                ),
            }
            fallback_hint = (
                "अगर चाहें तो मैं 2-3 योजनाएँ सीधे सुझाव दूँ, या हम आपकी प्रोफ़ाइल के हिसाब से चुनें।"
                if lang == "hi"
                else "If you want, I can suggest 2-3 schemes directly, or narrow it by your profile."
            )
            rag_response["next_step"] = f"{rag_response['next_step']} {fallback_hint}"

        intent = INTENT_SCHEME_QUERY
        session["last_intent"] = intent
        session["last_action"] = "info"
        response_text = format_info_text(rag_response, lang)
        if need_confidence < low_threshold:
            low_conf = (
                "कृपया बताएं कि आपकी प्राथमिकता क्या है: पैसे की मदद, स्वास्थ्य, या घर?"
                if lang == "hi"
                else "Please clarify your top priority: financial support, health, or housing?"
            )
            response_text = f"{response_text}\n\n{low_conf}"
        elif need_confidence > high_threshold and explainable:
            guidance = "\n".join(f"- {item['scheme']}: {item['reason']}" for item in explainable)
            response_text = f"{response_text}\n\n{guidance}"
        if explainable:
            response_text = f"{response_text}\n\n{_confidence_explanation_line(lang, str(explainable[0].get('reason') or ''))}"
        if short_mode:
            response_text = _short_answer(response_text, lang)
        response_text = f"{response_text}\n\n{_recommendation_confirmation_prompt(lang)}"
        response_text = f"{response_text}{_recommendation_suffix(lang, recommendations)}" if recommendations else response_text
        _append_history(session, "assistant", response_text)

        scheme_details = build_scheme_details(intent, rag_response)
        if has_match and scheme_details and scheme_details.get("title"):
            selected_scheme = resolve_scheme_name(scheme_details.get("title"))
            session["last_scheme"] = scheme_details.get("title")
            session["selected_scheme"] = selected_scheme
            session["field_completion"] = {field: bool(session.get("field_completion", {}).get(field, False)) for field in _session_fields(session)}
            session["next_field"] = get_next_field(session)
            _mark_accepted_scheme(session, str(scheme_details.get("title") or ""))

        if recommendations:
            top_scheme_name = recommendations[0]
            top_scheme = None
            for item in explainable:
                if item.get("scheme") == top_scheme_name:
                    top_scheme = item
                    break
            if top_scheme:
                session["last_recommendation_reason"] = top_scheme.get("reason")

        quick_actions = build_recommendation_quick_actions(recommendations, lang)

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
        if not session.get("selected_scheme"):
            derived_scheme = resolve_scheme_name(session.get("last_scheme") or get_default_scheme_for_category(need_category))
            session["selected_scheme"] = derived_scheme
            session["field_completion"] = {field: False for field in _session_fields(session)}
            session["next_field"] = get_next_field(session)

        if session.get("action_confirmation_pending", False):
            if _is_affirmative(cleaned_input):
                session["action_confirmation_pending"] = False
            elif _is_negative(cleaned_input):
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
        question = get_field_question(current_field, lang)
        strict_message = (
            f"इस चरण को छोड़ा नहीं जा सकता। {question}"
            if lang == "hi"
            else f"This step cannot be skipped. {question}"
        )
        _append_history(session, "assistant", strict_message)
        update_session(session_id, session)
        return _build_response(
            session_id=session_id,
            response_text=strict_message,
            field_name=current_field,
            validation_passed=False,
            validation_error="step_cannot_skip",
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
        extracted = _extract_multi_field_values(cleaned_input)
        if extracted:
            extraction_result = _apply_extracted_fields(session, extracted, lang)
            if extraction_result.get("conflicts"):
                session["extraction_conflicts"] = extraction_result.get("conflicts")
                option_field = next(iter(session["extraction_conflicts"].keys()))
                options = session["extraction_conflicts"][option_field]
                option_text = "; ".join(f"{idx + 1}. {value}" for idx, value in enumerate(options))
                prompt = (
                    f"मुझे {FIELD_LABELS.get(option_field, {}).get('hi', option_field)} के लिए कई मान मिले। सही विकल्प चुनें: {option_text}"
                    if lang == "hi"
                    else f"I detected multiple values for {FIELD_LABELS.get(option_field, {}).get('en', option_field)}. Please choose: {option_text}"
                )
                _append_history(session, "assistant", prompt)
                update_session(session_id, session)
                return _build_response(
                    session_id=session_id,
                    response_text=prompt,
                    field_name=option_field,
                    validation_passed=False,
                    validation_error="extraction_conflict",
                    session_complete=False,
                    mode="clarify",
                    action="resolve_extraction_conflict",
                    session=session,
                    quick_actions=build_quick_actions(lang, "clarify", "resolve_extraction_conflict", session.get("last_scheme"), False),
                )

            if extraction_result.get("low_confidence"):
                field = next(iter(extraction_result["low_confidence"].keys()))
                prompt = (
                    f"मैंने {FIELD_LABELS.get(field, {}).get('hi', field)} का एक मान पकड़ा है, लेकिन भरोसा कम है। कृपया पुष्टि करें। {get_field_question(field, lang)}"
                    if lang == "hi"
                    else f"I detected a {FIELD_LABELS.get(field, {}).get('en', field)} value with low confidence. Please confirm it. {get_field_question(field, lang)}"
                )
                _append_history(session, "assistant", prompt)
                update_session(session_id, session)
                return _build_response(
                    session_id=session_id,
                    response_text=prompt,
                    field_name=field,
                    validation_passed=False,
                    validation_error="extraction_low_confidence",
                    session_complete=False,
                    mode="clarify",
                    action="confirm_extraction",
                    session=session,
                    quick_actions=build_quick_actions(lang, "clarify", "confirm_extraction", session.get("last_scheme"), False),
                )

            if extraction_result.get("applied"):
                next_after_extract = get_next_field(session)
                session["next_field"] = next_after_extract
                if next_after_extract is None:
                    session["confirmation_state"] = "pending"
                    session["dialogue_state"] = "confirming"
                    summary = _build_confirmation_summary(session, lang)
                    _append_history(session, "assistant", summary)
                    update_session(session_id, session)
                    return _build_response(
                        session_id=session_id,
                        response_text=summary,
                        field_name=None,
                        validation_passed=True,
                        validation_error=None,
                        session_complete=False,
                        mode="action",
                        action="confirm_details",
                        session=session,
                        quick_actions=build_quick_actions(lang, "action", "confirm_details", session.get("last_scheme"), False),
                    )
                question = get_field_question(next_after_extract, lang)
                _append_history(session, "assistant", question)
                update_session(session_id, session)
                return _build_response(
                    session_id=session_id,
                    response_text=question,
                    field_name=next_after_extract,
                    validation_passed=True,
                    validation_error=None,
                    session_complete=False,
                    mode="action",
                    action="collect_next_field",
                    session=session,
                    quick_actions=build_quick_actions(lang, "action", "collect_next_field", session.get("last_scheme"), False),
                )

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

        validation = validate_field(current_field, candidate_value, language=lang)
        if not validation.get("valid"):
            attempts = session.setdefault("invalid_attempts", {})
            attempts[current_field] = int(attempts.get(current_field, 0)) + 1
            retry_message = str(validation.get("error_message") or _validation_error_message(current_field, "invalid", lang))
            question = get_field_question(current_field, lang)
            if attempts[current_field] >= MAX_INVALID_ATTEMPTS_PER_FIELD:
                helper = (
                    "लगता है यह चरण कठिन हो रहा है। आप 'restart' बोलकर नई शुरुआत कर सकते हैं, या मैं उदाहरण देकर मदद करूँ।"
                    if lang == "hi"
                    else "This step seems difficult. You can say 'restart' to begin again, or I can guide with examples."
                )
                merged_message = f"{retry_message}. {helper}"
            else:
                merged_message = f"{retry_message}. {question}"
            _append_history(session, "assistant", merged_message)
            update_session(session_id, session)
            return _build_response(
                session_id=session_id,
                response_text=merged_message,
                field_name=current_field,
                validation_passed=False,
                validation_error=str(validation.get("error_code") or "invalid_input"),
                session_complete=False,
                session=session,
                quick_actions=build_quick_actions(lang, "action", "confirm_action_start" if attempts[current_field] >= MAX_INVALID_ATTEMPTS_PER_FIELD else None, session.get("last_scheme"), False),
            )

        session.setdefault("user_profile", {})[current_field] = str(validation.get("normalized") or "")
        session.setdefault("field_completion", {})[current_field] = True
        session.setdefault("invalid_attempts", {})[current_field] = 0
        active_fields = _session_fields(session)
        session["last_completed_field_index"] = active_fields.index(current_field) if current_field in active_fields else -1

    next_field = get_next_field(session)
    session["next_field"] = next_field
    session["session_complete"] = False

    if next_field is None:
        if not session.get("confirmation_done", False):
            session["confirmation_state"] = "pending"
            session["dialogue_state"] = "confirming"
            confirmation_text = _build_confirmation_summary(session, lang)
            confirmation_text = (
                f"{confirmation_text}\n\nकृपया सब जानकारी देखकर हाँ कहें या बदलाव बताएं।"
                if lang == "hi"
                else f"{confirmation_text}\n\nPlease review all details and say yes to submit, or ask to change any field."
            )
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
        session["dialogue_state"] = "completed"
        completion_message = f"{get_field_question(None, lang)}\n\n{_closing_summary(session, lang)}"
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
    session["dialogue_state"] = "collecting_info"

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
        log_event(
            "conversation_service_start",
            endpoint="conversation_service",
            status="started",
            session_id=session_id,
            user_input=(user_input or "")[:220],
            user_input_length=len(user_input or ""),
        )
        try:
            result = handle_conversation(session_id=session_id, user_input=user_input, language=language, debug=debug)
            # Enrich session with compact semantic memory for context-aware follow-up replies.
            session = get_session(session_id)
            _update_semantic_memory(session, user_input, result, result.get("primary_intent") or "")
            update_session(session_id, session)
            fallback_used = bool(((result.get("intent_debug") or {}).get("fallback_used")) or False)
            log_event(
                "conversation_service_success",
                endpoint="conversation_service",
                status="success",
                session_id=session_id,
                user_input=(user_input or "")[:220],
                detected_intent=result.get("primary_intent"),
                confidence=(result.get("intent_debug") or {}).get("confidence"),
                selected_scheme=session.get("selected_scheme") or session.get("last_scheme"),
                fallback_used=fallback_used,
            )
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
