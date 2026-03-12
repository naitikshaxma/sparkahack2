from typing import Tuple

from .bert_service import predict_intent
from .rag_service import retrieve_scheme
from .text_normalizer import normalize_text

INTENT_THRESHOLD = 0.35

RESPONSES = {
    "account_balance": {
        "en": {
            "confirmation": "Checking your account balance.",
            "explanation": "Your balance is 24,530 rupees.",
            "next_step": "Would you like recent transactions?",
        },
        "hi": {
            "confirmation": "आपका खाता बैलेंस देखा जा रहा है।",
            "explanation": "आपके खाते में 24,530 रुपये हैं।",
            "next_step": "क्या आप हाल की लेनदेन देखना चाहते हैं?",
        },
    },
    "apply_loan": {
        "en": {
            "confirmation": "I can help with loan application information.",
            "explanation": "You can apply for personal, home, or business loans through eligible channels.",
            "next_step": "Would you like the required documents list?",
        },
        "hi": {
            "confirmation": "मैं लोन आवेदन की जानकारी देने में मदद कर सकता हूँ।",
            "explanation": "आप व्यक्तिगत, गृह या व्यवसाय ऋण के लिए पात्र चैनलों से आवेदन कर सकते हैं।",
            "next_step": "क्या आप जरूरी दस्तावेजों की सूची जानना चाहते हैं?",
        },
    },
    "check_application_status": {
        "en": {
            "confirmation": "I can help check your application status.",
            "explanation": "Please keep your application reference number ready for status tracking.",
            "next_step": "Would you like step-by-step tracking guidance?",
        },
        "hi": {
            "confirmation": "मैं आपके आवेदन की स्थिति देखने में मदद कर सकता हूँ।",
            "explanation": "कृपया स्टेटस ट्रैक करने के लिए अपना आवेदन संदर्भ नंबर तैयार रखें।",
            "next_step": "क्या आप स्टेटस जांचने के चरण जानना चाहते हैं?",
        },
    },
    "register_complaint": {
        "en": {
            "confirmation": "I can help you register a complaint.",
            "explanation": "Please share your issue details, department, and location to proceed.",
            "next_step": "Would you like a complaint registration checklist?",
        },
        "hi": {
            "confirmation": "मैं शिकायत दर्ज कराने में आपकी मदद कर सकता हूँ।",
            "explanation": "आगे बढ़ने के लिए कृपया समस्या, विभाग और स्थान की जानकारी दें।",
            "next_step": "क्या आप शिकायत दर्ज करने की चेकलिस्ट चाहते हैं?",
        },
    },
    "unknown": {
        "en": {
            "confirmation": "I couldn't understand your request.",
            "explanation": "Please try asking again in a short sentence.",
            "next_step": "You can ask about government schemes, loans, or complaints.",
        },
        "hi": {
            "confirmation": "मैं आपकी बात समझ नहीं पाया।",
            "explanation": "कृपया एक छोटे वाक्य में फिर से पूछें।",
            "next_step": "आप सरकारी योजनाओं, लोन या शिकायत के बारे में पूछ सकते हैं।",
        },
    },
}


def _debug_print(label: str, value: object) -> None:
    safe_value = str(value).encode("unicode_escape").decode("ascii")
    print(label, safe_value)


def generate_response(language: str, transcript: str) -> Tuple[dict, str, float]:
    lang = "hi" if (language or "").strip().lower() == "hi" else "en"

    # 1) RAG first
    print("Transcript:", transcript)
    print("Normalized query:", normalize_text(transcript))
    print("Checking scheme retrieval...")
    scheme = retrieve_scheme(transcript, lang)
    if scheme:
        intent = "scheme_query"
        confidence = 1.0
        _debug_print("Detected intent:", intent)
        _debug_print("Confidence:", confidence)
        return scheme, intent, confidence

    # 2) Intent model only after RAG miss
    intent, confidence = predict_intent(transcript)
    confidence = float(confidence)
    if intent not in RESPONSES:
        intent = "unknown"

    # 3) Threshold fallback for non-scheme intents only
    if intent != "unknown" and confidence < INTENT_THRESHOLD:
        intent = "unknown"

    _debug_print("Detected intent:", intent)
    _debug_print("Confidence:", confidence)
    return RESPONSES[intent][lang], intent, confidence
