from typing import Any, Dict, List, Optional

from .validator import validate


DEFAULT_SCHEME_NAME = "Loan Assistance"

FIELD_QUESTIONS = {
    "full_name": {
        "en": "Please share your full name.",
        "hi": "कृपया अपना पूरा नाम बताएं।",
    },
    "phone": {
        "en": "Please share your 10-digit mobile number.",
        "hi": "कृपया अपना 10 अंकों का मोबाइल नंबर बताएं।",
    },
    "aadhaar_number": {
        "en": "Please share your 12-digit Aadhaar number.",
        "hi": "कृपया अपना 12 अंकों का आधार नंबर बताएं।",
    },
    "annual_income": {
        "en": "Please share your annual income.",
        "hi": "कृपया अपनी वार्षिक आय बताएं।",
    },
    "land_holding_acres": {
        "en": "Please share your total land holding in acres.",
        "hi": "कृपया अपनी कुल भूमि (एकड़ में) बताएं।",
    },
    "farmer_id": {
        "en": "Please share your farmer ID or registration number.",
        "hi": "कृपया अपना किसान आईडी या पंजीकरण नंबर बताएं।",
    },
    "health_card_number": {
        "en": "Please share your health card number if available.",
        "hi": "यदि उपलब्ध हो, तो कृपया अपना हेल्थ कार्ड नंबर बताएं।",
    },
    "family_size": {
        "en": "Please share your family size.",
        "hi": "कृपया परिवार के सदस्यों की संख्या बताएं।",
    },
    "residential_status": {
        "en": "Please share your residential status (urban or rural).",
        "hi": "कृपया अपना आवासीय क्षेत्र बताएं (शहरी या ग्रामीण)।",
    },
    "property_ownership": {
        "en": "Please share whether you own a house or land.",
        "hi": "कृपया बताएं कि आपके पास घर या जमीन है या नहीं।",
    },
}

SCHEME_FORM_CONFIG = {
    "pm kisan": {
        "fields": ["full_name", "aadhaar_number", "phone", "land_holding_acres", "annual_income", "farmer_id"],
        "category": "financial",
        "target_user": "farmer",
        "benefits_type": "financial",
    },
    "ayushman bharat": {
        "fields": ["full_name", "aadhaar_number", "phone", "family_size", "annual_income", "health_card_number"],
        "category": "health",
        "target_user": "family",
        "benefits_type": "health",
    },
    "pmay": {
        "fields": ["full_name", "aadhaar_number", "phone", "annual_income", "residential_status", "property_ownership"],
        "category": "housing",
        "target_user": "low_income",
        "benefits_type": "housing",
    },
    "loan assistance": {
        "fields": ["full_name", "phone", "aadhaar_number", "annual_income"],
        "category": "financial",
        "target_user": "general",
        "benefits_type": "financial",
    },
}

SCHEME_ALIASES = {
    "pm kisan": "pm kisan",
    "pm किसान": "pm kisan",
    "प्रधानमंत्री किसान": "pm kisan",
    "ayushman": "ayushman bharat",
    "ayushman bharat": "ayushman bharat",
    "pmay": "pmay",
    "pm आवास": "pmay",
    "housing": "pmay",
    "loan": "loan assistance",
    "loans": "loan assistance",
}


def resolve_scheme_name(scheme_name: Optional[str]) -> str:
    raw = (scheme_name or "").strip().lower()
    if not raw:
        return DEFAULT_SCHEME_NAME
    if raw in SCHEME_FORM_CONFIG:
        return raw
    for alias, canonical in SCHEME_ALIASES.items():
        if alias in raw:
            return canonical
    return raw if raw in SCHEME_FORM_CONFIG else "loan assistance"


def get_default_scheme_for_category(category: Optional[str]) -> str:
    value = (category or "").strip().lower()
    if value == "health":
        return "ayushman bharat"
    if value == "housing":
        return "pmay"
    if value == "financial":
        return "pm kisan"
    return "loan assistance"


def get_fields_for_scheme(scheme_name: Optional[str]) -> List[str]:
    canonical = resolve_scheme_name(scheme_name)
    config = SCHEME_FORM_CONFIG.get(canonical, SCHEME_FORM_CONFIG["loan assistance"])
    return list(config.get("fields", SCHEME_FORM_CONFIG["loan assistance"]["fields"]))


def ensure_dynamic_field_completion(session: Dict[str, Any]) -> Dict[str, bool]:
    scheme_name = session.get("selected_scheme") or DEFAULT_SCHEME_NAME
    fields = get_fields_for_scheme(scheme_name)
    completion = dict(session.get("field_completion", {}))
    for field in fields:
        completion.setdefault(field, False)

    # Keep only active dynamic fields.
    filtered = {field: bool(completion.get(field, False)) for field in fields}
    session["field_completion"] = filtered
    return filtered


def get_next_field(session: Dict[str, Any]) -> Optional[str]:
    fields = get_fields_for_scheme(session.get("selected_scheme") or DEFAULT_SCHEME_NAME)
    field_completion = ensure_dynamic_field_completion(session)
    for field in fields:
        if not field_completion.get(field, False):
            return field
    return None


def get_previous_field(current_field: Optional[str], session: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if not current_field:
        return None
    fields = get_fields_for_scheme((session or {}).get("selected_scheme") or DEFAULT_SCHEME_NAME)
    try:
        index = fields.index(current_field)
    except ValueError:
        return None
    if index <= 0:
        return None
    return fields[index - 1]


def get_field_question(field: Optional[str], language: str = "en", scheme_name: Optional[str] = None) -> str:
    if not field:
        return (
            "Thank you. Your scheme application form is complete."
            if language == "en"
            else "धन्यवाद। आपका योजना आवेदन फॉर्म पूरा हो गया है।"
        )
    entry = FIELD_QUESTIONS.get(field)
    if not entry:
        return "Please provide the next required detail." if language == "en" else "कृपया अगली आवश्यक जानकारी बताएं।"
    return entry.get("en") if language == "en" else entry.get("hi")


# Backward-compatible alias for older call sites.
LOAN_FIELDS = get_fields_for_scheme("loan assistance")


def validate_field(field: str, value: str, language: str = "en") -> Dict[str, Any]:
    """Central validation engine for dynamic form fields.

    Returns API-safe payload with bilingual, user-facing error text.
    """
    is_valid, normalized, error_message = validate(field, value)
    lang = "hi" if (language or "").strip().lower() == "hi" else "en"

    if is_valid:
        return {
            "valid": True,
            "normalized": normalized,
            "error_code": None,
            "error_message": None,
        }

    code = "invalid_input"
    if field == "phone":
        code = "invalid_phone"
    elif field == "aadhaar_number":
        code = "invalid_aadhaar"
    elif field == "annual_income":
        code = "invalid_income"

    localized = {
        "invalid_phone": {
            "en": "Please enter a valid 10-digit mobile number.",
            "hi": "कृपया सही 10 अंकों का मोबाइल नंबर दर्ज करें।",
        },
        "invalid_aadhaar": {
            "en": "Please enter a valid 12-digit Aadhaar number.",
            "hi": "कृपया सही 12 अंकों का आधार नंबर दर्ज करें।",
        },
        "invalid_income": {
            "en": "Please enter annual income as numbers only.",
            "hi": "कृपया वार्षिक आय केवल संख्याओं में दर्ज करें।",
        },
        "invalid_input": {
            "en": "The value looks invalid. Please try again.",
            "hi": "दर्ज की गई जानकारी सही नहीं लग रही। कृपया दोबारा बताएं।",
        },
    }

    message = localized.get(code, localized["invalid_input"]).get(lang) or error_message or localized["invalid_input"]["en"]
    return {
        "valid": False,
        "normalized": None,
        "error_code": code,
        "error_message": message,
    }
