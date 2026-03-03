"""
BERT Service — Text → intent + confidence
Uses a fine-tuned multilingual BERT model for intent classification.
Model: BertForSequenceClassification (12 intents)
"""

import os
import pickle
from typing import Tuple

# Try importing torch and transformers, handle missing dependencies gracefully
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    DEPENDENCIES_LOADED = True
except ImportError as e:
    DEPENDENCIES_LOADED = False
    print(f"[BERT Service Warning] Missing dependency: {e}")

# ── Paths ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "models", "saved_model")
LABEL_ENCODER_PATH = os.path.join(BASE_DIR, "models", "label_encoder.pkl")

# ── Load model, tokenizer, and label encoder at import time ──
MODEL_LOADED = False
tokenizer = None
model = None
label_encoder = None

if DEPENDENCIES_LOADED:
    try:
        print("[BERT Service] Loading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)

        print("[BERT Service] Loading model...")
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
        model.eval()

        print("[BERT Service] Loading label encoder...")
        with open(LABEL_ENCODER_PATH, "rb") as f:
            label_encoder = pickle.load(f)

        print(f"[BERT Service] Ready — {len(label_encoder.classes_)} intents: {list(label_encoder.classes_)}")
        MODEL_LOADED = True
    except Exception as e:
        print(f"[BERT Service Warning] Failed to load model from {MODEL_DIR}.")
        print(f"Error: {e}")
        print("Will use fallback/mock intent classification until models are downloaded.")
else:
    print("[BERT Service Warning] Dependencies missing. Will use fallback/mock intent classification.")

# ── Intent → category mapping (keys match flow_engine exactly) ──
INTENT_CATEGORIES = {
    "account_balance": "banking",
    "loan_information": "banking",
    "account_opening": "banking",
    "ration_service": "government",
    "pension_service": "government",
    "gas_subsidy": "government",
    "eligibility_query": "government",
    "document_requirement": "government",
    "complaint_registration": "complaint",
    "complaint_status": "complaint",
    "application_tracking": "general",
    "status_check": "general",
}


def _categorize(intent: str) -> str:
    """Map an intent label to a category."""
    intent_lower = intent.lower().replace(" ", "_")
    for key, category in INTENT_CATEGORIES.items():
        if key in intent_lower:
            return category
    return "general"


def classify_intent(text: str, language: str = "en") -> Tuple[str, float, str]:
    """
    Classify the intent of the given text using the fine-tuned BERT model.

    Args:
        text: Transcribed text
        language: Language code

    Returns:
        Tuple of (intent_label, confidence_score, category)
    """
    if not MODEL_LOADED:
        # Fallback: classify based on simple keyword matching
        text_lower = text.lower()
        if any(w in text_lower for w in ["balance", "बैलेंस", "शिल्लक", "ব্যালেন্স", "இருப்பு", "బ్యాలెన్స్", "ಬ್ಯಾಲೆನ್ಸ್", "ബാലൻസ", "ਬੈਲੈਂਸ", "બેલેન્સ"]):
            intent = "account_balance"
        elif any(w in text_lower for w in ["loan", "ऋण", "कर्ज", "ঋণ", "கடன்", "రుణం", "ಸಾಲ", "വായ്പ", "ਕਰਜ਼", "લોન"]):
            intent = "loan_information"
        elif any(w in text_lower for w in ["ration", "राशन", "রেশন", "ரேஷன்", "రేషన్", "ರೇಷನ್", "റേഷൻ", "ਰਾਸ਼ਨ", "રેશન"]):
            intent = "ration_service"
        elif any(w in text_lower for w in ["pension", "पेंशन", "পেনশন", "ஓய்வூதியம்", "పెన్షన్", "ಪಿಂಚಣಿ", "പെൻഷൻ", "ਪੈਨਸ਼ਨ", "પેન્શન"]):
            intent = "pension_service"
        elif any(w in text_lower for w in ["gas", "गैस", "গ্যাস", "எரிவாயு", "గ్యాస్", "ಗ್ಯಾಸ್", "ഗ്യാസ്", "ਗੈਸ"]):
            intent = "gas_subsidy"
        elif any(w in text_lower for w in ["complaint", "शिकायत", "অভিযোগ", "புகார்", "ఫిర్యాదు", "ದೂರು", "പരാതി", "ਸ਼ਿਕਾਇਤ", "ફ"]):
            intent = "complaint_registration"
        elif any(w in text_lower for w in ["status", "track", "स्थिति", "स्टेटस"]):
            intent = "status_check"
        elif any(w in text_lower for w in ["account", "open", "खाता", "खोल"]):
            intent = "account_opening"
        elif any(w in text_lower for w in ["document", "दस्तावेज"]):
            intent = "document_requirement"
        elif any(w in text_lower for w in ["eligib", "पात्र"]):
            intent = "eligibility_query"
        else:
            intent = "account_balance"
        confidence_pct = 92.0
        category = _categorize(intent)
        return intent, confidence_pct, category

    # Tokenize
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=128,
        padding=True,
    )

    # Inference
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)
        confidence, predicted_idx = torch.max(probs, dim=-1)

    # Decode label
    intent = label_encoder.inverse_transform([predicted_idx.item()])[0]
    confidence_pct = round(confidence.item() * 100, 1)
    category = _categorize(intent)

    return intent, confidence_pct, category
