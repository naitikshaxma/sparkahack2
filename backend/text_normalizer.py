import re
import unicodedata

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
    "کسان": "kisan",
    "योजना": "scheme",
    "योजनाएं": "scheme",
    "योजनाओं": "scheme",
    "yojana": "scheme",
    "yojna": "scheme",
    "scheme": "scheme",
    "یوجنا": "scheme",
    "راشن": "ration",
    "राशन": "ration",
    "rashan": "ration",
    "raashan": "ration",
    "rashani": "ration",
    "raashani": "ration",
    "rashaani": "ration",
    "ration": "ration",
    "कार्ड": "card",
    "कार्डों": "card",
    "card": "card",
    "kard": "card",
    "kardr": "card",
    "cardr": "card",
    "کارڈ": "card",
    "आयुष्मान": "ayushman",
    "ayushman": "ayushman",
    "ایوشمان": "ayushman",
    "भारत": "bharat",
    "bharat": "bharat",
    "بھارت": "bharat",
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
    "kese",
    "kaise",
    "about",
    "batao",
    "bataye",
    "batayen",
    "batayein",
    "बताएं",
    "बताइए",
    "बताओ",
    "banwaye",
    "banvaye",
    "banvayen",
    "जानकारी",
    "जानना",
    "बारे",
    "ہو",
    "کے",
    "میں",
    "کیا",
    "کیسے",
}


def _replace_phrases(text: str) -> str:
    output = text
    for phrase in sorted(PHRASE_MAP, key=len, reverse=True):
        output = output.replace(phrase, PHRASE_MAP[phrase])
    return output


def normalize_text(text: str) -> str:
    raw = unicodedata.normalize("NFKC", str(text or "")).lower().strip()
    if not raw:
        return ""

    normalized = _replace_phrases(raw)
    normalized = re.sub(r"[^\w\s\u0900-\u097f\u0600-\u06ff]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    mapped_tokens = []
    for token in normalized.split():
        mapped = WORD_MAP.get(token, token)
        if mapped in STOPWORDS:
            continue
        if mapped_tokens and mapped_tokens[-1] == mapped:
            continue
        mapped_tokens.append(mapped)

    return " ".join(mapped_tokens).strip()
