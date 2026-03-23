from __future__ import annotations

from difflib import SequenceMatcher
from typing import Dict, List, Optional

from .intents import (
    INTENT_APPLY_LOAN,
    INTENT_CHECK_APPLICATION_STATUS,
    INTENT_GENERAL_QUERY,
    INTENT_SCHEME_QUERY,
    VALID_INTENTS,
    calibrate_confidence,
    get_intent_threshold,
    migrate_intent,
    normalize_intent,
)


_INTENT_KEYWORDS: Dict[str, List[str]] = {
    INTENT_APPLY_LOAN: ["apply", "loan", "application", "apply now", "start application", "loan chahiye"],
    INTENT_CHECK_APPLICATION_STATUS: ["status", "track", "reference", "application status", "check status"],
    "register_complaint": ["complaint", "issue", "problem", "register complaint", "grievance"],
    "account_balance": ["balance", "account balance", "bank balance", "saldo"],
    INTENT_SCHEME_QUERY: ["scheme", "yojana", "benefits", "eligibility", "documents", "information"],
}


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def detect_multi_intents(text: str) -> List[str]:
    query = _normalize_text(text)
    if not query:
        return []

    scored: List[tuple[str, int]] = []
    for intent, keywords in _INTENT_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in query:
                score += 2 if " " in keyword else 1
        if score > 0:
            scored.append((intent, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    intents = [intent for intent, _ in scored]
    return intents


def _closest_intent_by_similarity(text: str) -> Optional[str]:
    query = _normalize_text(text)
    if not query:
        return None

    best_intent = None
    best_score = 0.0
    for intent, keywords in _INTENT_KEYWORDS.items():
        for keyword in keywords:
            score = SequenceMatcher(a=query, b=keyword).ratio()
            if score > best_score:
                best_score = score
                best_intent = intent

    if best_score >= 0.55:
        return best_intent
    return None


def resolve_intent_decision(
    raw_intent: str,
    raw_confidence: float,
    text: str,
    session_context: Optional[dict] = None,
) -> dict:
    session_context = session_context or {}

    migrated_intent, migration_used = migrate_intent(raw_intent)
    normalized_intent, recognized = normalize_intent(migrated_intent)

    multi_intents = detect_multi_intents(text)
    if not multi_intents and normalized_intent in VALID_INTENTS:
        multi_intents = [normalized_intent]

    primary_intent = multi_intents[0] if multi_intents else normalized_intent
    secondary_intents = [intent for intent in multi_intents[1:] if intent != primary_intent]

    calibrated_confidence, keyword_boost_used = calibrate_confidence(raw_confidence, primary_intent, text)
    threshold = get_intent_threshold(primary_intent)
    low_confidence = calibrated_confidence < threshold

    context_used = False
    context_source = ""
    if low_confidence:
        previous_intent, ok = normalize_intent(session_context.get("last_intent"))
        if ok:
            primary_intent = previous_intent
            context_used = True
            context_source = "last_intent"
            calibrated_confidence = max(calibrated_confidence, threshold)
            low_confidence = False
        else:
            last_action = _normalize_text(str(session_context.get("last_action", "")))
            if "apply" in last_action:
                primary_intent = INTENT_APPLY_LOAN
                context_used = True
                context_source = "last_action"
                calibrated_confidence = max(calibrated_confidence, get_intent_threshold(INTENT_APPLY_LOAN))
                low_confidence = False
            elif "status" in last_action:
                primary_intent = INTENT_CHECK_APPLICATION_STATUS
                context_used = True
                context_source = "last_action"
                calibrated_confidence = max(calibrated_confidence, get_intent_threshold(INTENT_CHECK_APPLICATION_STATUS))
                low_confidence = False

    fallback_used = False
    fallback_reason = ""
    if low_confidence:
        closest = _closest_intent_by_similarity(text)
        if closest:
            primary_intent = closest
            fallback_reason = "closest_partial_match"
        else:
            primary_intent = INTENT_GENERAL_QUERY
            fallback_reason = "low_confidence_no_partial_match"
        fallback_used = True

    if primary_intent not in VALID_INTENTS:
        primary_intent = INTENT_GENERAL_QUERY
        fallback_used = True
        fallback_reason = fallback_reason or "unrecognized_intent"

    secondary_intents = [intent for intent in secondary_intents if intent in VALID_INTENTS and intent != primary_intent]

    return {
        "raw_intent": raw_intent,
        "migrated_intent": migrated_intent,
        "migration_used": migration_used,
        "normalized_intent": normalized_intent,
        "recognized": recognized,
        "primary_intent": primary_intent,
        "secondary_intents": secondary_intents,
        "confidence": float(calibrated_confidence),
        "raw_confidence": float(raw_confidence),
        "threshold": float(get_intent_threshold(primary_intent)),
        "low_confidence": bool(float(calibrated_confidence) < get_intent_threshold(primary_intent)),
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "context_used": context_used,
        "context_source": context_source,
        "keyword_boost_used": keyword_boost_used,
    }
