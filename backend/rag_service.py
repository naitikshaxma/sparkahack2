import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from rapidfuzz import fuzz

from .text_normalizer import normalize_text

DATA_PATH = Path(__file__).resolve().parent.parent / "datasets" / "schemes_dataset.json"
logger = logging.getLogger(__name__)
REQUIRED_FIELDS = {
    "name",
    "keywords",
    "summary_en",
    "summary_hi",
    "details_en",
    "details_hi",
    "eligibility_en",
    "eligibility_hi",
    "description_en",
    "description_hi",
}

SCHEME_ALIASES = {
    "pm kisan": [
        "pm kesan",
        "pm kesant",
        "pm cassant",
        "pm cassan",
        "pm kasan",
        "pm kesson",
        "pm kesan scheme",
        "pm cassant scheme",
        "p m cassant scheme",
    ]
}

GENERIC_KEYWORDS = {
    "scheme",
    "apply",
    "application",
    "process",
    "status",
    "help",
    "online",
    "documents",
    "eligibility",
    "benefits",
    "portal",
    "registration",
    "official",
}


def _load_schemes() -> List[dict]:
    with open(DATA_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, list):
        raise ValueError("schemes_dataset.json must contain a list.")

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Scheme at index {idx} is not an object.")
        missing = REQUIRED_FIELDS - set(item.keys())
        if missing:
            raise ValueError(f"Scheme at index {idx} missing fields: {sorted(missing)}")
    return data


def _build_terms(scheme: dict) -> List[str]:
    terms: List[str] = []
    name = str(scheme.get("name", "")).strip()
    keywords = scheme.get("keywords", [])

    if isinstance(keywords, list):
        terms.extend(str(keyword) for keyword in keywords)

    if name:
        terms.append(name)
        terms.append(f"{name} scheme")
        terms.extend(SCHEME_ALIASES.get(name.lower(), []))

    normalized_terms = {normalize_text(term) for term in terms if normalize_text(term)}
    # Longer terms first to prefer exact scheme-level matches over short tokens.
    return sorted(normalized_terms, key=len, reverse=True)


SCHEMES = _load_schemes()
PREPARED_SCHEMES: List[Tuple[dict, List[str]]] = [(scheme, _build_terms(scheme)) for scheme in SCHEMES]


def _filter_generic_tokens(text: str) -> str:
    tokens = [token for token in text.split() if token not in GENERIC_KEYWORDS]
    return " ".join(tokens).strip()


def get_rag_status() -> dict:
    return {
        "dataset_path": str(DATA_PATH),
        "total_schemes": int(len(SCHEMES)),
        "loaded": True,
    }


def retrieve_scheme(transcript: str, language: str = "en") -> Optional[dict]:
    query = normalize_text(transcript)
    logger.debug("RAG retrieval query normalized")
    if not query:
        return None

    query_lower = query.lower()
    query_filtered = _filter_generic_tokens(query_lower)
    query_for_match = query_filtered or query_lower
    query_tokens = set(query_for_match.split())
    lang = "hi" if (language or "").strip().lower() == "hi" else "en"

    for scheme, terms in PREPARED_SCHEMES:
        for keyword in terms:
            keyword_lower = keyword.lower()
            keyword_filtered = _filter_generic_tokens(keyword_lower)
            keyword_for_match = keyword_filtered or keyword_lower
            keyword_tokens = set(keyword_for_match.split())

            overlap = keyword_tokens.intersection(query_tokens)
            if not overlap and len(keyword_tokens) > 1:
                continue

            score = fuzz.partial_ratio(keyword_for_match.lower(), query_for_match.lower())
            if len(keyword_tokens) > 1 and len(overlap) == 1 and score < 85:
                continue
            if score > 75:
                logger.debug("RAG keyword matched")
                if lang == "hi":
                    return {
                        "confirmation": scheme["summary_hi"],
                        "explanation": scheme["details_hi"],
                        "next_step": "क्या आप पात्रता या आवेदन प्रक्रिया जानना चाहते हैं?",
                    }
                return {
                    "confirmation": scheme["summary_en"],
                    "explanation": scheme["details_en"],
                    "next_step": "Would you like to know eligibility or how to apply?",
                }
    return None


def recommend_schemes(transcript: str, language: str = "en", limit: int = 3) -> List[str]:
    query = normalize_text(transcript)
    if not query:
        return [str(scheme.get("name", "")).strip() for scheme in SCHEMES[:limit] if scheme.get("name")]

    query_lower = query.lower()
    query_filtered = _filter_generic_tokens(query_lower)
    query_for_match = query_filtered or query_lower

    scored: List[Tuple[int, str]] = []
    for scheme, terms in PREPARED_SCHEMES:
        name = str(scheme.get("name", "")).strip()
        if not name:
            continue

        best = 0
        for term in terms:
            score = int(fuzz.partial_ratio(term.lower(), query_for_match.lower()))
            if score > best:
                best = score

        scored.append((best, name))

    scored.sort(key=lambda item: item[0], reverse=True)
    recommended = [name for _, name in scored[:limit]]
    if not recommended:
        return [str(scheme.get("name", "")).strip() for scheme in SCHEMES[:limit] if scheme.get("name")]
    return recommended
