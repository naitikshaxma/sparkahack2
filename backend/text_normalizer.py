import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional


PHRASE_MAP = {
    "प्रधानमंत्री किसान सम्मान निधि योजना": "pm kisan scheme",
    "प्रधानमंत्री किसान योजना": "pm kisan scheme",
    "पी एम किसान योजना": "pm kisan scheme",
    "पीएम किसान योजना": "pm kisan scheme",
    "पी एम": "pm",
    "पीएम": "pm",
    "p m": "pm",
    "pm kisan yojana": "pm kisan scheme",
    "kisan yojana": "kisan scheme",
    "आयुष्मान भारत योजना": "ayushman bharat scheme",
    "आयुष्मान भारत": "ayushman bharat",
    "प्रधानमंत्री आवास योजना": "pmay scheme",
    "आवास योजना": "housing scheme",
    "वृद्धा पेंशन": "old age pension",
    "राशन कार्ड योजना": "ration card scheme",
    "राशन कार्ड": "ration card",
    "راشن کارڈ": "ration card",
}

WORD_MAP = {
    "पीएम": "pm",
    "प्रधानमंत्री": "pm",
    "pm": "pm",
    "किसान": "kisan",
    "किसानो": "kisan",
    "किसानों": "kisan",
    "kisaan": "kisan",
    "kissan": "kisan",
    "kisan": "kisan",
    "योजना": "scheme",
    "योजनाएं": "scheme",
    "योजनाओं": "scheme",
    "yojana": "scheme",
    "yojna": "scheme",
    "scheme": "scheme",
    "loan": "loan",
    "rin": "loan",
    "ऋण": "loan",
    "लोन": "loan",
    "madad": "help",
    "मदद": "help",
    "sahayata": "help",
    "सहायता": "help",
    "apply": "apply",
    "aavedan": "apply",
    "आवेदन": "apply",
    "status": "status",
    "स्थिति": "status",
    "eligibility": "eligibility",
    "पात्रता": "eligibility",
    "benefits": "benefits",
    "लाभ": "benefits",
    "documents": "documents",
    "दस्तावेज": "documents",
    "document": "documents",
    "आयुष्मान": "ayushman",
    "ayushman": "ayushman",
    "भारत": "bharat",
    "bharat": "bharat",
    "राशन": "ration",
    "rashan": "ration",
    "कार्ड": "card",
    "card": "card",
}

STOPWORDS = {
    "के",
    "का",
    "की",
    "को",
    "से",
    "में",
    "मे",
    "पर",
    "और",
    "या",
    "कि",
    "kya",
    "ka",
    "ki",
    "ke",
    "ko",
    "se",
    "me",
    "mein",
    "hai",
    "hain",
    "ho",
    "hoga",
    "please",
    "plz",
    "about",
    "batao",
    "bataye",
    "batayen",
    "batayein",
    "बताएं",
    "बताइए",
    "बताओ",
    "जानकारी",
    "जानना",
    "bhi",
    "भी",
}

HINDI_SIGNAL_TOKENS = {
    "kya",
    "kaise",
    "yojana",
    "madad",
    "aavedan",
    "haan",
    "nahi",
    "ji",
}


@dataclass(frozen=True)
class NormalizedInput:
    raw_text: str
    normalized_text: str
    intent_text: str
    language: str
    tokens: List[str]


def _replace_phrases(text: str) -> str:
    output = text
    for phrase in sorted(PHRASE_MAP, key=len, reverse=True):
        output = output.replace(phrase, PHRASE_MAP[phrase])
    return output


def detect_text_language(text: str, language_hint: Optional[str] = None) -> str:
    hint = (language_hint or "").strip().lower()
    if hint in {"hi", "en"}:
        return hint

    content = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    if not content:
        return "en"

    if re.search(r"[\u0900-\u097F]", content):
        return "hi"

    tokens = set(content.split())
    if tokens.intersection(HINDI_SIGNAL_TOKENS):
        return "hi"
    return "en"


def _tokenize_core(text: str) -> List[str]:
    normalized = _replace_phrases(text)
    normalized = re.sub(r"[^\w\s\u0900-\u097f]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    tokens: List[str] = []
    for token in normalized.split():
        mapped = WORD_MAP.get(token, token)
        if mapped in STOPWORDS:
            continue
        if tokens and tokens[-1] == mapped:
            continue
        tokens.append(mapped)
    return tokens


def normalize_text(text: str) -> str:
    raw = unicodedata.normalize("NFKC", str(text or "")).lower().strip()
    if not raw:
        return ""
    return " ".join(_tokenize_core(raw)).strip()


def normalize_for_intent(text: str, language_hint: Optional[str] = None) -> NormalizedInput:
    raw_text = unicodedata.normalize("NFKC", str(text or "")).strip()
    lowered = raw_text.lower()
    normalized_text = normalize_text(lowered)
    intent_text = normalized_text or re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", lowered)).strip()
    tokens = intent_text.split() if intent_text else []
    language = detect_text_language(raw_text, language_hint=language_hint)
    return NormalizedInput(
        raw_text=raw_text,
        normalized_text=normalized_text,
        intent_text=intent_text,
        language=language,
        tokens=tokens,
    )
