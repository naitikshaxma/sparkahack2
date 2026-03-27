from typing import Optional, Set, Tuple

from backend.intents import (
    ACTION_INTENTS,
    INFO_INTENTS,
    INTENT_APPLY_LOAN,
    INTENT_GENERAL_QUERY,
    INTENT_SCHEME_QUERY,
    normalize_intent,
)


ACTION_KEYWORDS = {
    "apply",
    "application",
    "start form",
    "form bharna",
    "form fill",
    "fill",
    "register",
    "loan chahiye",
    "loan chaiye",
    "submit",
    "status",
    "track",
    "complaint",
    "loan",
    "autofill",
    "step",
}

INFO_KEYWORDS = {
    "what",
    "kya hai",
    "kya hota hai",
    "which",
    "tell me",
    "explain",
    "details",
    "about",
    "eligibility",
    "benefits",
    "scheme",
    "yojana",
    "pm",
    "process",
    "documents",
    "pm kisan",
    "pmay",
    "ayushman",
    "yojana",
}

FOLLOWUP_INFO_KEYWORDS = {
    "eligibility",
    "benefits",
    "documents",
    "how to apply",
    "apply process",
    "details",
    "more info",
    "more information",
}


def _contains_keyword(query: str, keywords: Set[str]) -> bool:
    lower = query.lower()
    return any(keyword in lower for keyword in keywords)


def detect_intent_and_mode(
    query: str,
    predicted_intent: Optional[str] = None,
    confidence: Optional[float] = None,
) -> Tuple[str, str]:
    text = (query or "").strip().lower()
    canonical_predicted_intent, _ = normalize_intent(predicted_intent, default=INTENT_GENERAL_QUERY)

    if not text:
        return INTENT_GENERAL_QUERY, "info"

    has_action = _contains_keyword(text, ACTION_KEYWORDS)
    has_info = _contains_keyword(text, INFO_KEYWORDS)

    # Prefer info when both signals exist to avoid forcing users into form mode.
    if has_action and has_info:
        return INTENT_SCHEME_QUERY, "info"

    if has_action:
        return INTENT_APPLY_LOAN, "action"

    if has_info:
        return INTENT_SCHEME_QUERY, "info"

    if canonical_predicted_intent in ACTION_INTENTS:
        return canonical_predicted_intent, "action"

    if canonical_predicted_intent in INFO_INTENTS:
        return canonical_predicted_intent, "info"

    if confidence is not None and confidence >= 0.65:
        return canonical_predicted_intent, "action"

    # Safer UX fallback is information mode.
    return INTENT_GENERAL_QUERY, "info"


def is_followup_info_query(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    return _contains_keyword(text, FOLLOWUP_INFO_KEYWORDS)
