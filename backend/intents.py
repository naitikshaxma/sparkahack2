import re
from typing import Optional, Tuple

INTENT_VERSION = "v1"


INTENT_APPLY_LOAN = "apply_loan"
INTENT_CHECK_APPLICATION_STATUS = "check_application_status"
INTENT_REGISTER_COMPLAINT = "register_complaint"
INTENT_SCHEME_QUERY = "scheme_query"
INTENT_GENERAL_QUERY = "general_query"
INTENT_ACCOUNT_BALANCE = "account_balance"

VALID_INTENTS = {
    INTENT_APPLY_LOAN,
    INTENT_CHECK_APPLICATION_STATUS,
    INTENT_REGISTER_COMPLAINT,
    INTENT_SCHEME_QUERY,
    INTENT_GENERAL_QUERY,
    INTENT_ACCOUNT_BALANCE,
}

ACTION_INTENTS = {
    INTENT_APPLY_LOAN,
    INTENT_CHECK_APPLICATION_STATUS,
    INTENT_REGISTER_COMPLAINT,
    INTENT_ACCOUNT_BALANCE,
}

INFO_INTENTS = {
    INTENT_SCHEME_QUERY,
    INTENT_GENERAL_QUERY,
}

INTENT_CONFIDENCE_THRESHOLD = 0.35
INTENT_CONFIDENCE_THRESHOLDS = {
    INTENT_APPLY_LOAN: 0.42,
    INTENT_CHECK_APPLICATION_STATUS: 0.48,
    INTENT_REGISTER_COMPLAINT: 0.46,
    INTENT_SCHEME_QUERY: 0.30,
    INTENT_GENERAL_QUERY: 0.20,
    INTENT_ACCOUNT_BALANCE: 0.52,
}

INTENT_MIGRATIONS = {
    "v0": {
        "loan_application": INTENT_APPLY_LOAN,
        "action_request": INTENT_APPLY_LOAN,
        "information_request": INTENT_SCHEME_QUERY,
        "unknown": INTENT_GENERAL_QUERY,
    }
}

INTENT_EXPORT_MAP = {
    "v1": {
        INTENT_APPLY_LOAN: INTENT_APPLY_LOAN,
        INTENT_CHECK_APPLICATION_STATUS: INTENT_CHECK_APPLICATION_STATUS,
        INTENT_REGISTER_COMPLAINT: INTENT_REGISTER_COMPLAINT,
        INTENT_SCHEME_QUERY: INTENT_SCHEME_QUERY,
        INTENT_GENERAL_QUERY: INTENT_GENERAL_QUERY,
        INTENT_ACCOUNT_BALANCE: INTENT_ACCOUNT_BALANCE,
    },
    "v0": {
        INTENT_APPLY_LOAN: "loan_application",
        INTENT_CHECK_APPLICATION_STATUS: "application_status",
        INTENT_REGISTER_COMPLAINT: "complaint",
        INTENT_SCHEME_QUERY: "information_request",
        INTENT_GENERAL_QUERY: "unknown",
        INTENT_ACCOUNT_BALANCE: "balance_check",
    },
}

_INTENT_ALIASES = {
    "applyloan": INTENT_APPLY_LOAN,
    "apply_loan": INTENT_APPLY_LOAN,
    "loan_application": INTENT_APPLY_LOAN,
    "loan": INTENT_APPLY_LOAN,
    "action_request": INTENT_APPLY_LOAN,
    "check_application_status": INTENT_CHECK_APPLICATION_STATUS,
    "application_status": INTENT_CHECK_APPLICATION_STATUS,
    "status_check": INTENT_CHECK_APPLICATION_STATUS,
    "account_balance": INTENT_ACCOUNT_BALANCE,
    "balance_check": INTENT_ACCOUNT_BALANCE,
    "check_balance": INTENT_ACCOUNT_BALANCE,
    "register_complaint": INTENT_REGISTER_COMPLAINT,
    "complaint": INTENT_REGISTER_COMPLAINT,
    "scheme_query": INTENT_SCHEME_QUERY,
    "information_request": INTENT_SCHEME_QUERY,
    "info_request": INTENT_SCHEME_QUERY,
    "general_query": INTENT_GENERAL_QUERY,
    "general": INTENT_GENERAL_QUERY,
    "unknown": INTENT_GENERAL_QUERY,
    "fallback": INTENT_GENERAL_QUERY,
}


def _normalize_label(label: Optional[str]) -> str:
    cleaned = (label or "").strip().lower()
    if not cleaned:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")


def normalize_intent(label: Optional[str], default: str = INTENT_GENERAL_QUERY) -> Tuple[str, bool]:
    normalized = _normalize_label(label)
    if normalized in VALID_INTENTS:
        return normalized, True
    if normalized in _INTENT_ALIASES:
        return _INTENT_ALIASES[normalized], True
    return default, False


def migrate_intent(label: Optional[str], from_version: str = "v0") -> Tuple[str, bool]:
    normalized = _normalize_label(label)
    if not normalized:
        return "", False

    mapping = INTENT_MIGRATIONS.get(from_version, {})
    if normalized in mapping:
        return mapping[normalized], True
    return normalized, False


def export_intent(label: Optional[str], target_version: str = INTENT_VERSION) -> str:
    normalized, _ = normalize_intent(label)
    mapping = INTENT_EXPORT_MAP.get(target_version, INTENT_EXPORT_MAP[INTENT_VERSION])
    return mapping.get(normalized, mapping.get(INTENT_GENERAL_QUERY, INTENT_GENERAL_QUERY))


def get_intent_threshold(intent: str) -> float:
    return float(INTENT_CONFIDENCE_THRESHOLDS.get(intent, INTENT_CONFIDENCE_THRESHOLD))


def calibrate_confidence(score: float, intent: str, text: str = "") -> Tuple[float, bool]:
    calibrated = max(0.0, min(1.0, float(score)))
    lowered = (text or "").strip().lower()

    strong_keyword_hit = False
    if intent == INTENT_APPLY_LOAN and any(term in lowered for term in {"apply loan", "loan apply", "start application"}):
        calibrated = min(1.0, calibrated + 0.15)
        strong_keyword_hit = True
    elif intent == INTENT_CHECK_APPLICATION_STATUS and any(term in lowered for term in {"check status", "application status", "track status"}):
        calibrated = min(1.0, calibrated + 0.15)
        strong_keyword_hit = True
    elif intent == INTENT_REGISTER_COMPLAINT and any(term in lowered for term in {"register complaint", "file complaint", "raise complaint"}):
        calibrated = min(1.0, calibrated + 0.15)
        strong_keyword_hit = True
    elif intent == INTENT_SCHEME_QUERY and any(term in lowered for term in {"eligibility", "benefits", "scheme details", "yojana"}):
        calibrated = min(1.0, calibrated + 0.12)
        strong_keyword_hit = True

    return calibrated, strong_keyword_hit


def apply_confidence_fallback(
    intent: str,
    confidence: float,
    threshold: float = INTENT_CONFIDENCE_THRESHOLD,
) -> Tuple[str, bool]:
    resolved_threshold = threshold if threshold != INTENT_CONFIDENCE_THRESHOLD else get_intent_threshold(intent)
    if confidence < resolved_threshold and intent != INTENT_SCHEME_QUERY:
        return INTENT_GENERAL_QUERY, True
    return intent, False


def normalize_intent_prediction(
    raw_intent: Optional[str],
    confidence: float,
    threshold: float = INTENT_CONFIDENCE_THRESHOLD,
    text: str = "",
) -> Tuple[str, float, bool]:
    migrated, _ = migrate_intent(raw_intent)
    canonical_intent, _ = normalize_intent(migrated or raw_intent)
    calibrated_confidence, _ = calibrate_confidence(float(confidence), canonical_intent, text)
    canonical_intent, used_fallback = apply_confidence_fallback(canonical_intent, calibrated_confidence, threshold=threshold)
    return canonical_intent, float(calibrated_confidence), used_fallback
