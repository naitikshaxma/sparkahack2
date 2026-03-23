from typing import Any, Dict, Optional


LOAN_FIELDS = [
    "full_name",
    "phone",
    "aadhaar_number",
    "annual_income",
]

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
}


def get_next_field(session: Dict[str, Any]) -> Optional[str]:
    field_completion = session.get("field_completion", {})
    for field in LOAN_FIELDS:
        if not field_completion.get(field, False):
            return field
    return None


def get_previous_field(current_field: Optional[str]) -> Optional[str]:
    if not current_field:
        return None
    try:
        index = LOAN_FIELDS.index(current_field)
    except ValueError:
        return None
    if index <= 0:
        return None
    return LOAN_FIELDS[index - 1]


def get_field_question(field: Optional[str], language: str = "en") -> str:
    if not field:
        return (
            "Thank you. Your loan application form is complete."
            if language == "en"
            else "धन्यवाद। आपका ऋण आवेदन फॉर्म पूरा हो गया है।"
        )
    entry = FIELD_QUESTIONS.get(field)
    if not entry:
        return "Please provide the next required detail." if language == "en" else "कृपया अगली आवश्यक जानकारी बताएं।"
    return entry.get("en") if language == "en" else entry.get("hi")
