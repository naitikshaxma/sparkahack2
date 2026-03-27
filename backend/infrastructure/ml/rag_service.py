import json
import logging
import os
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from backend.dataset_validator import DatasetValidationError, validate_and_normalize_schemes
from backend.application.engines.eligibility import check_eligibility
from backend.core.metrics import increment_counter, record_timing
from backend.text_normalizer import normalize_text
from backend.utils.perf_cache import LruTtlCache, stable_hash

DATA_PATH = Path(__file__).resolve().parent.parent / "datasets" / "schemes_dataset.json"
logger = logging.getLogger(__name__)
REQUIRED_FIELDS = {
    "id",
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
    "category",
    "target_user",
    "required_fields",
    "benefits_type",
    "income_limit",
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

SCHEME_METADATA_FALLBACK: Dict[str, Dict[str, object]] = {
    "pm kisan": {
        "category": "financial",
        "target_user": "farmer",
        "required_fields": ["full_name", "aadhaar_number", "phone", "land_holding_acres", "annual_income", "farmer_id"],
        "benefits_type": "financial",
        "income_limit": 800000,
    },
    "ayushman bharat": {
        "category": "health",
        "target_user": "general",
        "required_fields": ["full_name", "aadhaar_number", "phone", "family_size", "annual_income", "health_card_number"],
        "benefits_type": "insurance",
        "income_limit": 500000,
    },
    "pmay": {
        "category": "housing",
        "target_user": "low_income",
        "required_fields": ["full_name", "aadhaar_number", "phone", "annual_income", "residential_status", "property_ownership"],
        "benefits_type": "housing",
        "income_limit": 600000,
    },
    "loan assistance": {
        "category": "financial",
        "target_user": "general",
        "required_fields": ["full_name", "phone", "aadhaar_number", "annual_income"],
        "benefits_type": "loan",
        "income_limit": 1000000,
    },
}

CATEGORY_KEYWORD_HINTS: Dict[str, set[str]] = {
    "financial": {"loan", "credit", "subsidy", "finance", "bank"},
    "health": {"health", "medical", "hospital", "insurance", "treatment", "ayushman"},
    "housing": {"housing", "house", "home", "pmay", "rent", "property"},
    "education": {"education", "school", "college", "student", "scholarship", "tuition"},
    "employment": {"employment", "job", "rojgar", "skill", "training", "work", "startup"},
    "agriculture": {"agriculture", "farmer", "kisan", "crop", "krishi", "irrigation"},
    "social_welfare": {"pension", "welfare", "social", "ration", "old age", "widow", "disability"},
}

TARGET_USER_HINTS: Dict[str, set[str]] = {
    "farmer": {"farmer", "kisan", "krishi", "crop"},
    "student": {"student", "school", "college", "scholarship"},
    "business": {"business", "entrepreneur", "startup", "shop", "msme"},
}

BENEFITS_TYPE_HINTS: Dict[str, set[str]] = {
    "subsidy": {"subsidy", "grant", "assistance", "aid", "support"},
    "loan": {"loan", "credit", "kcc", "finance"},
    "insurance": {"insurance", "bima", "coverage", "pmjay", "ayushman"},
    "pension": {"pension", "retirement", "old age"},
    "scholarship": {"scholarship", "education", "tuition", "stipend"},
    "employment": {"job", "employment", "training", "skill", "livelihood"},
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

INELIGIBILITY_EXCLUDE_THRESHOLD = 0.25
DIVERSITY_SIMILARITY_THRESHOLD = 85
MIN_SCORING_WEIGHT = 0.10
MAX_SCORING_WEIGHT = 0.55

RAG_CACHE_MAXSIZE = max(128, int((os.getenv("RAG_CACHE_MAXSIZE") or "1024").strip() or "1024"))
RAG_CACHE_TTL_SECONDS = max(5.0, float((os.getenv("RAG_CACHE_TTL_SECONDS") or "180").strip() or "180"))
RAG_DATASET_WATCH_INTERVAL_SECONDS = max(1.0, float((os.getenv("RAG_DATASET_WATCH_INTERVAL_SECONDS") or "5").strip() or "5"))

_STATE_LOCK = threading.RLock()
_RANKED_CACHE = LruTtlCache(maxsize=RAG_CACHE_MAXSIZE, ttl_seconds=RAG_CACHE_TTL_SECONDS)
_RECOMMEND_CACHE = LruTtlCache(maxsize=RAG_CACHE_MAXSIZE, ttl_seconds=RAG_CACHE_TTL_SECONDS)
_REASON_CACHE = LruTtlCache(maxsize=RAG_CACHE_MAXSIZE, ttl_seconds=RAG_CACHE_TTL_SECONDS)
_RETRIEVE_CACHE = LruTtlCache(maxsize=RAG_CACHE_MAXSIZE, ttl_seconds=RAG_CACHE_TTL_SECONDS)

_LAST_DATASET_MTIME = 0.0
_LAST_DATASET_WATCH_TS = 0.0
_LAST_PROFILE_SIGNATURE = ""


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _profile_completeness_score(user_profile: Optional[Dict[str, str]]) -> float:
    profile = user_profile or {}
    if not isinstance(profile, dict) or not profile:
        return 0.0

    considered_keys = {
        "user_type",
        "income_range",
        "annual_income",
        "occupation",
        "location",
        "family_size",
        "land_holding_acres",
        "residential_status",
    }
    present = 0
    for key in considered_keys:
        value = str(profile.get(key) or "").strip()
        if value:
            present += 1
    return _clamp01(present / float(len(considered_keys)))


def _confidence_signal(query: str, context_fusion: Optional[Dict[str, object]]) -> float:
    fused = context_fusion or {}
    for key in ("confidence", "need_confidence", "query_confidence", "intent_confidence"):
        raw = fused.get(key)
        if raw in {None, ""}:
            continue
        try:
            return _clamp01(float(raw))
        except (TypeError, ValueError):
            continue

    tokens = [token for token in query.split() if token]
    if not tokens:
        return 0.35

    informative = [token for token in tokens if token not in GENERIC_KEYWORDS and len(token) > 2]
    token_factor = min(1.0, len(tokens) / 12.0)
    specificity = (len(informative) / len(tokens)) if tokens else 0.0
    # Heuristic confidence when upstream signal is not available.
    return _clamp01(0.35 + (0.35 * token_factor) + (0.30 * specificity))


def _dynamic_scoring_weights(query: str, confidence: float, profile_completeness: float) -> Dict[str, float]:
    weights = {
        "embedding": 0.40,
        "keyword": 0.20,
        "category": 0.20,
        "eligibility": 0.20,
    }

    token_count = len([token for token in query.split() if token])
    if token_count <= 3:
        weights["keyword"] += 0.08
        weights["embedding"] -= 0.08
    elif token_count >= 10:
        weights["embedding"] += 0.10
        weights["keyword"] -= 0.10

    if confidence < 0.50:
        weights["category"] += 0.08
        weights["eligibility"] += 0.06
        weights["embedding"] -= 0.07
        weights["keyword"] -= 0.07
    elif confidence > 0.80:
        weights["embedding"] += 0.05
        weights["keyword"] += 0.03
        weights["category"] -= 0.04
        weights["eligibility"] -= 0.04

    if profile_completeness >= 0.50:
        weights["eligibility"] += 0.08
        weights["keyword"] -= 0.04
        weights["embedding"] -= 0.04

    return _bound_and_normalize_weights(
        weights,
        minimum=MIN_SCORING_WEIGHT,
        maximum=MAX_SCORING_WEIGHT,
    )


def _bound_and_normalize_weights(
    weights: Dict[str, float],
    *,
    minimum: float,
    maximum: float,
) -> Dict[str, float]:
    if not weights:
        return {}

    keys = list(weights.keys())
    count = len(keys)
    if minimum * count > 1.0:
        minimum = 1.0 / count
    if maximum * count < 1.0:
        maximum = 1.0 / count

    raw = {key: max(0.0, float(weights.get(key, 0.0))) for key in keys}
    bounded: Dict[str, float] = {}
    remaining_keys = set(keys)
    remaining_total = 1.0

    while remaining_keys:
        raw_sum = sum(raw[key] for key in remaining_keys)
        if raw_sum <= 0:
            even_share = remaining_total / float(len(remaining_keys))
            for key in list(remaining_keys):
                raw[key] = even_share
            raw_sum = remaining_total

        constrained = False
        for key in list(remaining_keys):
            proposed = remaining_total * (raw[key] / raw_sum)
            if proposed < minimum:
                bounded[key] = minimum
                remaining_total -= minimum
                remaining_keys.remove(key)
                constrained = True
            elif proposed > maximum:
                bounded[key] = maximum
                remaining_total -= maximum
                remaining_keys.remove(key)
                constrained = True

        if not constrained:
            for key in list(remaining_keys):
                bounded[key] = remaining_total * (raw[key] / raw_sum)
                remaining_keys.remove(key)

    total = sum(bounded.values())
    if total <= 0:
        fallback = 1.0 / float(count)
        return {key: fallback for key in keys}
    normalized = {key: value / total for key, value in bounded.items()}
    return normalized


def _scheme_category(scheme: dict) -> str:
    return normalize_text(str(scheme.get("category") or "")) or "general"


def _scheme_similarity(left: dict, right: dict) -> int:
    left_name = str(left.get("name") or "").strip()
    right_name = str(right.get("name") or "").strip()
    left_keywords = " ".join(str(k) for k in (left.get("keywords") or []) if str(k).strip())
    right_keywords = " ".join(str(k) for k in (right.get("keywords") or []) if str(k).strip())
    left_blob = f"{left_name} {left_keywords}".strip()
    right_blob = f"{right_name} {right_keywords}".strip()
    if not left_blob or not right_blob:
        return 0
    return int(fuzz.token_set_ratio(normalize_text(left_blob), normalize_text(right_blob)))


def _select_diverse_top(ranked: List[Tuple[int, dict]], limit: int) -> List[Tuple[int, dict]]:
    if limit <= 0:
        return []
    if not ranked:
        return []

    # Keep top-1 stable and apply diversity only to remaining slots.
    selected: List[Tuple[int, dict]] = [ranked[0]]
    selected_categories: set[str] = {_scheme_category(ranked[0][1])}
    skipped_similarity: List[str] = []
    skipped_category_bias: List[str] = []
    kept_names: List[str] = [str(ranked[0][1].get("name") or "").strip()]

    for score, scheme in ranked[1:]:
        if len(selected) >= limit:
            break
        category = _scheme_category(scheme)
        if any(_scheme_similarity(scheme, existing) >= DIVERSITY_SIMILARITY_THRESHOLD for _, existing in selected):
            skipped_similarity.append(str(scheme.get("name") or "").strip())
            continue

        # In top-3, prefer adding a new category whenever possible.
        if len(selected) < 3 and selected_categories and category in selected_categories:
            alternate_exists = any(
                _scheme_category(candidate) not in selected_categories
                and not any(
                    _scheme_similarity(candidate, existing) >= DIVERSITY_SIMILARITY_THRESHOLD
                    for _, existing in selected
                )
                for _, candidate in ranked[1:]
            )
            if alternate_exists:
                skipped_category_bias.append(str(scheme.get("name") or "").strip())
                continue

        selected.append((score, scheme))
        selected_categories.add(category)
        kept_names.append(str(scheme.get("name") or "").strip())

    # Relax similarity rule slightly if strict diversity under-fills.
    if len(selected) < limit:
        for score, scheme in ranked[1:]:
            if any(existing is scheme for _, existing in selected):
                continue
            if any(_scheme_similarity(scheme, existing) >= 92 for _, existing in selected):
                continue
            selected.append((score, scheme))
            kept_names.append(str(scheme.get("name") or "").strip())
            if len(selected) >= limit:
                break

    # Ensure at least two categories in top-3 if possible.
    first_n = selected[: min(3, len(selected))]
    if len(first_n) >= 2:
        categories = {_scheme_category(scheme) for _, scheme in first_n}
        if len(categories) < 2:
            for score, candidate in ranked:
                candidate_category = _scheme_category(candidate)
                if candidate_category in categories:
                    continue
                if any(_scheme_similarity(candidate, existing) >= 90 for _, existing in first_n[:-1]):
                    continue
                if len(selected) >= 3:
                    selected[2] = (score, candidate)
                elif len(selected) >= 2:
                    selected[-1] = (score, candidate)
                break

    logger.debug(
        "RAG diversity filtering fixed_top1=%s selected=%s skipped_similarity=%s skipped_category_bias=%s",
        str(ranked[0][1].get("name") or "").strip(),
        kept_names,
        skipped_similarity[:10],
        skipped_category_bias[:10],
    )

    return selected[:limit]


def _profile_relevance_label(profile_score: int) -> str:
    if profile_score >= 70:
        return "high"
    if profile_score >= 35:
        return "medium"
    return "low"


def _explain_reason(
    scheme: dict,
    *,
    need_category: Optional[str],
    user_profile: Optional[Dict[str, str]],
) -> str:
    scheme_category = normalize_text(str(scheme.get("category", "")))
    requested_category = normalize_text(str(need_category or ""))
    category_match = "yes" if requested_category and scheme_category == requested_category else "no"

    eligibility = check_eligibility(user_profile or {}, scheme)
    eligibility_score = int(round(_clamp01(float(eligibility.get("score", 0.0))) * 100))
    eligibility_match = "eligible" if bool(eligibility.get("eligible", False)) else "weak"

    profile_score = _user_profile_score(scheme, user_profile)
    profile_relevance = _profile_relevance_label(profile_score)

    return (
        f"Category match: {category_match}"
        f"; Eligibility match: {eligibility_match} ({eligibility_score}%)"
        f"; Profile relevance: {profile_relevance} ({profile_score}%)."
    )


def _popular_schemes_by_category(limit: int, preferred_category: Optional[str] = None) -> List[str]:
    if limit <= 0:
        return []

    preferred = normalize_text(str(preferred_category or ""))
    by_category: Dict[str, List[str]] = {}
    for scheme in SCHEMES:
        name = str(scheme.get("name") or "").strip()
        if not name:
            continue
        category = _scheme_category(scheme)
        by_category.setdefault(category, []).append(name)

    ordered_categories: List[str] = []
    if preferred and preferred in by_category:
        ordered_categories.append(preferred)
    ordered_categories.extend(sorted(cat for cat in by_category.keys() if cat != preferred))

    picks: List[str] = []
    cursor = {cat: 0 for cat in ordered_categories}
    while len(picks) < limit and ordered_categories:
        progressed = False
        for category in ordered_categories:
            idx = cursor[category]
            if idx >= len(by_category.get(category, [])):
                continue
            picks.append(by_category[category][idx])
            cursor[category] += 1
            progressed = True
            if len(picks) >= limit:
                break
        if not progressed:
            break
    return picks


def _cold_start_mode(query: str, user_profile: Optional[Dict[str, str]]) -> bool:
    if _profile_completeness_score(user_profile) > 0:
        return False
    return len([token for token in query.split() if token]) <= 2


def _load_schemes() -> List[dict]:
    with open(DATA_PATH, "r", encoding="utf-8") as handle:
        raw_data = json.load(handle)

    try:
        data = validate_and_normalize_schemes(raw_data, dataset_name=DATA_PATH.name)
    except DatasetValidationError as exc:
        raise RuntimeError(
            f"Startup failed: dataset validation error in {DATA_PATH.name}. {exc}"
        ) from exc

    enriched: List[dict] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Scheme at index {idx} is not an object.")

        name = str(item.get("name", "")).strip()
        canonical = normalize_text(name)
        fallback = SCHEME_METADATA_FALLBACK.get(canonical, SCHEME_METADATA_FALLBACK["loan assistance"])

        keywords = item.get("keywords", [])
        keywords_text = " ".join(str(keyword) for keyword in keywords) if isinstance(keywords, list) else ""
        searchable_text = normalize_text(f"{name} {keywords_text}")

        def _infer_category() -> str:
            if str(item.get("category") or "").strip():
                return str(item.get("category") or "").strip().lower()
            best_category = str(fallback["category"])
            best_score = 0
            for category, hints in CATEGORY_KEYWORD_HINTS.items():
                score = sum(1 for hint in hints if hint in searchable_text)
                if score > best_score:
                    best_score = score
                    best_category = category
            return best_category

        def _infer_target_user() -> str:
            existing = str(item.get("target_user") or "").strip().lower()
            if existing:
                return existing
            best_target = str(fallback["target_user"])
            best_score = 0
            for target, hints in TARGET_USER_HINTS.items():
                score = sum(1 for hint in hints if hint in searchable_text)
                if score > best_score:
                    best_score = score
                    best_target = target
            return best_target or "general"

        def _infer_benefits_type() -> str:
            existing = str(item.get("benefits_type") or "").strip().lower()
            if existing:
                return existing
            best_type = str(fallback["benefits_type"])
            best_score = 0
            for benefit_type, hints in BENEFITS_TYPE_HINTS.items():
                score = sum(1 for hint in hints if hint in searchable_text)
                if score > best_score:
                    best_score = score
                    best_type = benefit_type
            return best_type

        raw_limit = item.get("income_limit")
        if raw_limit in {"", None}:
            income_limit: Any = fallback.get("income_limit")
        else:
            income_limit = raw_limit

        item["category"] = _infer_category()
        item["target_user"] = _infer_target_user()
        item.setdefault("required_fields", list(fallback["required_fields"]))
        item["benefits_type"] = _infer_benefits_type()
        item["income_limit"] = income_limit

        missing = REQUIRED_FIELDS - set(item.keys())
        if missing:
            raise ValueError(f"Scheme at index {idx} missing fields after enrichment: {sorted(missing)}")
        enriched.append(item)

    # Deduplicate by scheme name to keep results stable.
    seen: set[str] = set()
    deduped: List[dict] = []
    for item in enriched:
        key = normalize_text(str(item.get("name", "")).strip())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


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


def _build_scheme_blob(scheme: dict) -> str:
    chunks: List[str] = []
    for key in ("name", "summary_en", "summary_hi", "description_en", "description_hi"):
        value = str(scheme.get(key, "")).strip()
        if value:
            chunks.append(value)

    keywords = scheme.get("keywords", [])
    if isinstance(keywords, list):
        chunks.extend(str(keyword) for keyword in keywords if str(keyword).strip())

    return normalize_text(" ".join(chunks))


SCHEMES: List[dict] = []
PREPARED_SCHEMES: List[Tuple[dict, List[str]]] = []
SCHEME_BLOBS: List[Tuple[dict, str]] = []
SCHEME_BY_ID: Dict[str, dict] = {}


def _clear_rag_caches() -> None:
    _RANKED_CACHE.clear()
    _RECOMMEND_CACHE.clear()
    _REASON_CACHE.clear()
    _RETRIEVE_CACHE.clear()


def _initialize_precomputed_resources(*, precompute_embeddings: bool) -> None:
    global SCHEMES, PREPARED_SCHEMES, SCHEME_BLOBS, SCHEME_BY_ID
    global _LAST_DATASET_MTIME, _LAST_DATASET_WATCH_TS

    schemes = _load_schemes()
    prepared = [(scheme, _build_terms(scheme)) for scheme in schemes]
    blobs = [(scheme, _build_scheme_blob(scheme)) for scheme in schemes]
    by_id = {str(scheme.get("id") or "").strip(): scheme for scheme in schemes if str(scheme.get("id") or "").strip()}

    with _STATE_LOCK:
        SCHEMES = schemes
        PREPARED_SCHEMES = prepared
        SCHEME_BLOBS = blobs
        SCHEME_BY_ID = by_id
        _LAST_DATASET_MTIME = DATA_PATH.stat().st_mtime if DATA_PATH.exists() else 0.0
        _LAST_DATASET_WATCH_TS = time.time()

    _clear_rag_caches()
    if precompute_embeddings:
        _refresh_scheme_embeddings(force=True)


def _profile_signature(user_profile: Optional[Dict[str, str]]) -> str:
    profile = user_profile or {}
    payload = {
        "user_type": normalize_text(str(profile.get("user_type") or "")),
        "income_range": normalize_text(str(profile.get("income_range") or "")),
        "annual_income": str(profile.get("annual_income") or "").replace(",", "").strip(),
        "location": normalize_text(str(profile.get("location") or "")),
    }
    return stable_hash(payload)


def _maybe_invalidate_profile_cache(user_profile: Optional[Dict[str, str]]) -> None:
    global _LAST_PROFILE_SIGNATURE
    signature = _profile_signature(user_profile)
    if not signature:
        return
    with _STATE_LOCK:
        previous = _LAST_PROFILE_SIGNATURE
        if previous and previous != signature:
            _RECOMMEND_CACHE.clear()
            _REASON_CACHE.clear()
            increment_counter("rag_cache_profile_invalidations", 1)
        _LAST_PROFILE_SIGNATURE = signature


def _watch_dataset_changes() -> None:
    global _LAST_DATASET_WATCH_TS
    now = time.time()
    if (now - _LAST_DATASET_WATCH_TS) < RAG_DATASET_WATCH_INTERVAL_SECONDS:
        return

    current_mtime = DATA_PATH.stat().st_mtime if DATA_PATH.exists() else 0.0
    needs_reload = False
    with _STATE_LOCK:
        if current_mtime > _LAST_DATASET_MTIME:
            needs_reload = True
        _LAST_DATASET_WATCH_TS = now

    if needs_reload:
        logger.info("RAG dataset changed on disk; reloading precomputed resources")
        _initialize_precomputed_resources(precompute_embeddings=True)
        increment_counter("rag_dataset_reload_count", 1)


def _filter_generic_tokens(text: str) -> str:
    tokens = [token for token in text.split() if token not in GENERIC_KEYWORDS]
    return " ".join(tokens).strip()


def get_rag_status() -> dict:
    embedding_payload = _refresh_scheme_embeddings(force=False) if _embedding_model() is not None else None
    return {
        "dataset_path": str(DATA_PATH),
        "total_schemes": int(len(SCHEMES)),
        "loaded": True,
        "embedding_precomputed": bool(embedding_payload and embedding_payload.get("by_id")),
        "rank_cache_size": _RANKED_CACHE.size(),
        "recommend_cache_size": _RECOMMEND_CACHE.size(),
        "reason_cache_size": _REASON_CACHE.size(),
    }


def invalidate_rag_caches() -> None:
    _clear_rag_caches()


def warmup_rag_resources(precompute_embeddings: bool = True) -> None:
    started = time.perf_counter()
    _initialize_precomputed_resources(precompute_embeddings=precompute_embeddings)
    record_timing("rag_warmup_ms", (time.perf_counter() - started) * 1000.0)
    increment_counter("rag_warmup_count", 1)


def _scheme_response(scheme: dict, language: str) -> dict:
    lang = "hi" if (language or "").strip().lower() == "hi" else "en"
    if lang == "hi":
        return {
            "confirmation": str(scheme.get("name", "")).strip(),
            "explanation": scheme.get("details_hi") or scheme.get("description_hi") or "",
            "next_step": "क्या आप पात्रता, दस्तावेज़ या आवेदन प्रक्रिया जानना चाहते हैं?",
        }
    return {
        "confirmation": str(scheme.get("name", "")).strip(),
        "explanation": scheme.get("details_en") or scheme.get("description_en") or "",
        "next_step": "Would you like eligibility, required documents, or application steps?",
    }


@lru_cache(maxsize=1)
def _embedding_model():
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        return SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    except Exception:
        return None


def _refresh_scheme_embeddings(*, force: bool = False) -> Dict[str, Any] | None:
    model = _embedding_model()
    if model is None:
        return None

    with _STATE_LOCK:
        cached = getattr(_refresh_scheme_embeddings, "_cache", None)
        if cached is not None and not force:
            return cached

    encoded: Dict[str, Any] = {}
    for scheme, blob in SCHEME_BLOBS:
        scheme_id = str(scheme.get("id") or "").strip()
        if not scheme_id or not blob:
            continue
        emb = model.encode([blob], normalize_embeddings=True)
        encoded[scheme_id] = emb

    payload = {"by_id": encoded}
    with _STATE_LOCK:
        setattr(_refresh_scheme_embeddings, "_cache", payload)
    return payload


def _compute_query_embedding(query: str) -> Any | None:
    model = _embedding_model()
    if model is None or not query:
        return None
    return model.encode([query], normalize_embeddings=True)


def _embedding_similarity_score(query_embedding: Any, scheme: dict) -> int:
    if query_embedding is None:
        return 0
    encoded = _refresh_scheme_embeddings(force=False)
    if encoded is None:
        return 0
    scheme_id = str(scheme.get("id") or "").strip()
    scheme_emb = encoded.get("by_id", {}).get(scheme_id)
    if scheme_emb is None:
        return 0

    from sentence_transformers import util  # type: ignore

    score = float(util.cos_sim(query_embedding, scheme_emb).max().item())
    return int(max(0.0, min(1.0, score)) * 100)


def _category_score(scheme: dict, need_category: Optional[str]) -> int:
    category = normalize_text(str(scheme.get("category", "")))
    needed = normalize_text(str(need_category or ""))
    if not needed:
        return 0
    return 100 if category == needed else 0


def _keyword_overlap_score(query: str, terms: List[str]) -> int:
    query_tokens = set(query.split())
    if not query_tokens:
        return 0

    best = 0
    for term in terms:
        term_tokens = set(term.split())
        if not term_tokens:
            continue
        overlap = len(query_tokens.intersection(term_tokens)) / max(1, len(term_tokens))
        score = int(overlap * 100)
        if score > best:
            best = score
    return best


def _user_profile_score(scheme: dict, user_profile: Optional[Dict[str, str]]) -> int:
    if not user_profile:
        return 0

    target = normalize_text(str(scheme.get("target_user", "")))
    user_type = normalize_text(str(user_profile.get("user_type") or ""))
    income_range = normalize_text(str(user_profile.get("income_range") or ""))

    score = 0
    if target and user_type and (target in user_type or user_type in target):
        score += 70
    income_limit = scheme.get("income_limit")
    income_value = str(user_profile.get("annual_income") or "").replace(",", "").strip()
    income_range_hint = normalize_text(str(user_profile.get("income_range") or ""))
    if income_limit not in {None, "", 0, "0"} and income_value:
        try:
            if float(income_value) <= float(income_limit):
                score += 30
        except (TypeError, ValueError):
            if any(token in income_range_hint for token in {"low", "below", "under"}):
                score += 15
    if scheme.get("benefits_type") in {"subsidy", "social_welfare"} and income_range and any(tag in income_range for tag in {"low", "below", "under"}):
        score += 10
    return min(100, score)


def _feedback_score(scheme: dict, feedback: Optional[Dict[str, object]]) -> int:
    if not feedback:
        return 0

    name = normalize_text(str(scheme.get("name", "")))
    rejected = {normalize_text(str(item)) for item in (feedback.get("rejected_schemes") or [])}
    accepted = normalize_text(str(feedback.get("accepted_scheme") or ""))
    accepted_category = normalize_text(str(feedback.get("accepted_category") or ""))
    rejected_counts = feedback.get("rejected_counts") or {}
    accepted_counts = feedback.get("accepted_counts") or {}

    score = 0
    if name in rejected:
        repeat_rejects = int(rejected_counts.get(name, 1) or 1) if isinstance(rejected_counts, dict) else 1
        score -= min(180, 110 + ((repeat_rejects - 1) * 25))
    if accepted and name == accepted:
        repeat_accepts = int(accepted_counts.get(name, 1) or 1) if isinstance(accepted_counts, dict) else 1
        score += min(170, 100 + ((repeat_accepts - 1) * 20))
    if isinstance(accepted_counts, dict):
        for accepted_name, count in accepted_counts.items():
            accepted_key = normalize_text(str(accepted_name))
            if not accepted_key or accepted_key == name:
                continue
            similarity = int(fuzz.token_set_ratio(name, accepted_key))
            if similarity >= 80:
                score += min(45, max(0, int(count or 1) * 10))
    if accepted_category and normalize_text(str(scheme.get("category", ""))) == accepted_category:
        score += 28
    return score


def _context_fusion_score(scheme: dict, context_fusion: Optional[Dict[str, object]]) -> int:
    if not context_fusion:
        return 0

    score = 0
    category = normalize_text(str(scheme.get("category", "")))
    target_user = normalize_text(str(scheme.get("target_user", "")))

    need_category = normalize_text(str(context_fusion.get("need_category") or ""))
    if need_category and category and need_category == category:
        score += 45

    for hint in context_fusion.get("profile_hints", []):
        normalized = normalize_text(str(hint))
        if not normalized:
            continue
        if "user_type:" in normalized and target_user and normalized.split(":", 1)[-1] in target_user:
            score += 35
        if "income_range:" in normalized and scheme.get("benefits_type") == "financial":
            score += 15

    current_intent = normalize_text(str(context_fusion.get("current_intent") or ""))
    if current_intent and "eligibility" in current_intent:
        score += 10

    return min(100, score)


def _score_scheme_match(
    query_for_match: str,
    scheme: dict,
    terms: List[str],
    blob: str,
    query_embedding: Any = None,
    need_category: Optional[str] = None,
    user_profile: Optional[Dict[str, str]] = None,
    session_feedback: Optional[Dict[str, object]] = None,
    context_fusion: Optional[Dict[str, object]] = None,
    eligibility: Optional[Dict[str, object]] = None,
    dynamic_weights: Optional[Dict[str, float]] = None,
) -> int:
    best = 0
    for term in terms:
        score = int(fuzz.partial_ratio(term.lower(), query_for_match.lower()))
        if score > best:
            best = score

    keyword_score = _keyword_overlap_score(query_for_match, terms)
    category_score = _category_score(scheme, need_category)
    profile_score = _user_profile_score(scheme, user_profile)
    embedding_score = _embedding_similarity_score(query_embedding, scheme)
    feedback_score = _feedback_score(scheme, session_feedback)
    context_score = _context_fusion_score(scheme, context_fusion)
    eligibility_info = eligibility or check_eligibility(user_profile or {}, scheme)
    eligibility_score = int(float(eligibility_info.get("score", 0.0)) * 100)
    weights = dynamic_weights or _dynamic_scoring_weights(
        query_for_match,
        confidence=_confidence_signal(query_for_match, context_fusion),
        profile_completeness=_profile_completeness_score(user_profile),
    )

    if keyword_score == 0 and blob:
        keyword_score = int(fuzz.token_set_ratio(query_for_match.lower(), blob.lower()))

    final_score = (
        weights["embedding"] * embedding_score
        + weights["keyword"] * keyword_score
        + weights["category"] * category_score
        + weights["eligibility"] * eligibility_score
    )

    personalization_boost = (
        0.12 * profile_score
        + 0.10 * max(-100, min(100, feedback_score))
        + 0.06 * context_score
    )
    weighted = final_score + personalization_boost
    if not eligibility_info.get("eligible", True):
        weighted -= 15
    return int(round(max(0.0, weighted)))


def _rank_schemes(
    query: str,
    need_category: Optional[str] = None,
    user_profile: Optional[Dict[str, str]] = None,
    session_feedback: Optional[Dict[str, object]] = None,
    context_fusion: Optional[Dict[str, object]] = None,
) -> List[Tuple[int, dict]]:
    rank_started = time.perf_counter()
    query_filtered = _filter_generic_tokens(query)
    query_for_match = query_filtered or query
    scored: List[Tuple[int, dict]] = []
    excluded: List[Dict[str, object]] = []
    confidence = _confidence_signal(query_for_match, context_fusion)
    completeness = _profile_completeness_score(user_profile)
    dynamic_weights = _dynamic_scoring_weights(query_for_match, confidence, completeness)
    query_embedding = _compute_query_embedding(query_for_match)

    for (scheme, terms), (_, blob) in zip(PREPARED_SCHEMES, SCHEME_BLOBS):
        eligibility = check_eligibility(user_profile or {}, scheme)
        eligibility_score = _clamp01(float(eligibility.get("score", 0.0)))
        if eligibility_score < INELIGIBILITY_EXCLUDE_THRESHOLD:
            excluded.append(
                {
                    "scheme": str(scheme.get("name") or "").strip(),
                    "eligibility_score": round(eligibility_score, 3),
                }
            )
            continue

        score = _score_scheme_match(
            query_for_match,
            scheme,
            terms,
            blob,
            query_embedding=query_embedding,
            need_category=need_category,
            user_profile=user_profile,
            session_feedback=session_feedback,
            context_fusion=context_fusion,
            eligibility=eligibility,
            dynamic_weights=dynamic_weights,
        )
        scored.append((score, scheme))

    # Robust fallback: do not return an empty list if strict exclusion removed all options.
    if not scored:
        for (scheme, terms), (_, blob) in zip(PREPARED_SCHEMES, SCHEME_BLOBS):
            score = _score_scheme_match(
                query_for_match,
                scheme,
                terms,
                blob,
                query_embedding=query_embedding,
                need_category=need_category,
                user_profile=user_profile,
                session_feedback=session_feedback,
                context_fusion=context_fusion,
                dynamic_weights=dynamic_weights,
            )
            scored.append((score, scheme))

    scored.sort(key=lambda item: item[0], reverse=True)
    logger.debug(
        "RAG ranking decision query=%s weights=%s excluded=%s ranked=%s",
        query_for_match[:140],
        {key: round(value, 3) for key, value in dynamic_weights.items()},
        excluded[:12],
        len(scored),
    )
    record_timing("rag_ranking_ms", (time.perf_counter() - rank_started) * 1000.0)
    return scored


def _rank_cache_key(
    query: str,
    need_category: Optional[str],
    user_profile: Optional[Dict[str, str]],
    session_feedback: Optional[Dict[str, object]],
    context_fusion: Optional[Dict[str, object]],
) -> str:
    payload = {
        "query": query,
        "need_category": normalize_text(str(need_category or "")),
        "user_profile": user_profile or {},
        "session_feedback": session_feedback or {},
        "context_fusion": context_fusion or {},
    }
    return stable_hash(payload)


def _rank_schemes_cached(
    query: str,
    need_category: Optional[str] = None,
    user_profile: Optional[Dict[str, str]] = None,
    session_feedback: Optional[Dict[str, object]] = None,
    context_fusion: Optional[Dict[str, object]] = None,
) -> List[Tuple[int, dict]]:
    cache_key = _rank_cache_key(query, need_category, user_profile, session_feedback, context_fusion)
    cached = _RANKED_CACHE.get(cache_key)
    if cached is not None:
        increment_counter("rag_rank_cache_hit", 1)
        rows: List[Tuple[int, dict]] = []
        for score, scheme_id in cached:
            scheme = SCHEME_BY_ID.get(str(scheme_id))
            if scheme is not None:
                rows.append((int(score), scheme))
        if rows:
            return rows

    increment_counter("rag_rank_cache_miss", 1)
    ranked = _rank_schemes(
        query,
        need_category=need_category,
        user_profile=user_profile,
        session_feedback=session_feedback,
        context_fusion=context_fusion,
    )
    serializable = [(int(score), str(scheme.get("id") or "").strip()) for score, scheme in ranked if str(scheme.get("id") or "").strip()]
    _RANKED_CACHE.set(cache_key, serializable)
    return ranked


def retrieve_scheme(
    transcript: str,
    language: str = "en",
    need_category: Optional[str] = None,
    user_profile: Optional[Dict[str, str]] = None,
    session_feedback: Optional[Dict[str, object]] = None,
    context_fusion: Optional[Dict[str, object]] = None,
) -> Optional[dict]:
    _watch_dataset_changes()
    _maybe_invalidate_profile_cache(user_profile)
    query = normalize_text(transcript)
    logger.debug("RAG retrieval query normalized")
    if not query:
        return None

    retrieve_cache_key = stable_hash(
        {
            "type": "retrieve_scheme",
            "query": query,
            "language": (language or "en").strip().lower(),
            "need_category": need_category or "",
            "user_profile": user_profile or {},
            "session_feedback": session_feedback or {},
            "context_fusion": context_fusion or {},
        }
    )
    cached = _RETRIEVE_CACHE.get(retrieve_cache_key)
    if cached is not None:
        increment_counter("rag_retrieve_cache_hit", 1)
        return cached
    increment_counter("rag_retrieve_cache_miss", 1)

    ranked = _rank_schemes_cached(
        query,
        need_category=need_category,
        user_profile=user_profile,
        session_feedback=session_feedback,
        context_fusion=context_fusion,
    )
    if not ranked:
        return None

    best_score, best_scheme = ranked[0]
    if best_score >= 72:
        logger.debug("RAG exact-ish match hit score=%s", best_score)
        response = _scheme_response(best_scheme, language)
        _RETRIEVE_CACHE.set(retrieve_cache_key, response)
        return response

    # Near match still returns informative scheme details for vague requests.
    if best_score >= 60:
        logger.debug("RAG near match hit score=%s", best_score)
        response = _scheme_response(best_scheme, language)
        if (language or "").strip().lower() == "hi":
            response["next_step"] = "यदि यह सही योजना नहीं है, तो मैं अन्य योजनाएँ भी सुझा सकता हूँ।"
        else:
            response["next_step"] = "If this is not the right scheme, I can suggest other relevant schemes too."
        _RETRIEVE_CACHE.set(retrieve_cache_key, response)
        return response

    return None


def recommend_schemes(
    transcript: str,
    language: str = "en",
    limit: int = 3,
    need_category: Optional[str] = None,
    user_profile: Optional[Dict[str, str]] = None,
    session_feedback: Optional[Dict[str, object]] = None,
    context_fusion: Optional[Dict[str, object]] = None,
) -> List[str]:
    _watch_dataset_changes()
    _maybe_invalidate_profile_cache(user_profile)
    query = normalize_text(transcript)

    recommend_cache_key = stable_hash(
        {
            "type": "recommend_schemes",
            "query": query,
            "language": (language or "en").strip().lower(),
            "limit": int(limit),
            "need_category": need_category or "",
            "user_profile": user_profile or {},
            "session_feedback": session_feedback or {},
            "context_fusion": context_fusion or {},
        }
    )
    cached = _RECOMMEND_CACHE.get(recommend_cache_key)
    if cached is not None:
        increment_counter("rag_recommend_cache_hit", 1)
        return list(cached)
    increment_counter("rag_recommend_cache_miss", 1)

    if _cold_start_mode(query, user_profile):
        names = _popular_schemes_by_category(limit=limit, preferred_category=need_category)
        _RECOMMEND_CACHE.set(recommend_cache_key, list(names))
        return names

    if not query:
        names = _popular_schemes_by_category(limit=limit, preferred_category=need_category)
        _RECOMMEND_CACHE.set(recommend_cache_key, list(names))
        return names

    ranked = _rank_schemes_cached(
        query,
        need_category=need_category,
        user_profile=user_profile,
        session_feedback=session_feedback,
        context_fusion=context_fusion,
    )
    ranked = _select_diverse_top(ranked, limit=max(limit, 3))

    scored: List[Tuple[int, str]] = []
    for score, scheme in ranked:
        name = str(scheme.get("name", "")).strip()
        if name:
            scored.append((score, name))

    recommended = [name for _, name in scored[:limit]]
    if not recommended:
        recommended = _popular_schemes_by_category(limit=limit, preferred_category=need_category)
    _RECOMMEND_CACHE.set(recommend_cache_key, list(recommended))
    return recommended


def retrieve_scheme_with_recommendations(
    transcript: str,
    language: str = "en",
    limit: int = 3,
    need_category: Optional[str] = None,
    user_profile: Optional[Dict[str, str]] = None,
    session_feedback: Optional[Dict[str, object]] = None,
    context_fusion: Optional[Dict[str, object]] = None,
) -> Tuple[Optional[dict], List[str], bool]:
    match = retrieve_scheme(
        transcript,
        language,
        need_category=need_category,
        user_profile=user_profile,
        session_feedback=session_feedback,
        context_fusion=context_fusion,
    )
    recommendations = recommend_schemes(
        transcript,
        language,
        limit=limit,
        need_category=need_category,
        user_profile=user_profile,
        session_feedback=session_feedback,
        context_fusion=context_fusion,
    )
    exact_match = bool(match is not None)
    return match, recommendations, exact_match


def recommend_schemes_with_reasons(
    transcript: str,
    language: str = "en",
    limit: int = 3,
    need_category: Optional[str] = None,
    user_profile: Optional[Dict[str, str]] = None,
    session_feedback: Optional[Dict[str, object]] = None,
    context_fusion: Optional[Dict[str, object]] = None,
) -> List[Dict[str, str]]:
    _watch_dataset_changes()
    _maybe_invalidate_profile_cache(user_profile)
    query = normalize_text(transcript)

    reason_cache_key = stable_hash(
        {
            "type": "recommend_schemes_with_reasons",
            "query": query,
            "language": (language or "en").strip().lower(),
            "limit": int(limit),
            "need_category": need_category or "",
            "user_profile": user_profile or {},
            "session_feedback": session_feedback or {},
            "context_fusion": context_fusion or {},
        }
    )
    cached_rows = _REASON_CACHE.get(reason_cache_key)
    if cached_rows is not None:
        increment_counter("rag_reason_cache_hit", 1)
        return list(cached_rows)
    increment_counter("rag_reason_cache_miss", 1)

    if _cold_start_mode(query, user_profile):
        names = _popular_schemes_by_category(limit=limit, preferred_category=need_category)
        cold_rows: List[Dict[str, str]] = []
        for name in names:
            scheme = next((item for item in SCHEMES if str(item.get("name", "")).strip() == name), None)
            summary = ""
            category = ""
            if scheme is not None:
                lang = "hi" if (language or "").strip().lower() == "hi" else "en"
                summary = str(scheme.get(f"summary_{lang}") or scheme.get("summary_en") or "").strip()
                category = str(scheme.get("category") or "").strip()
            cold_rows.append({
                "scheme": name,
                "summary": summary,
                "reason": (
                    f"Popular choice in {category or 'this'} category for new users. "
                    + _explain_reason(
                        scheme or {},
                        need_category=need_category,
                        user_profile=user_profile,
                    )
                ).strip(),
            })
        _REASON_CACHE.set(reason_cache_key, list(cold_rows))
        return cold_rows

    if not query:
        names = recommend_schemes(
            transcript,
            language,
            limit=limit,
            need_category=need_category,
            user_profile=user_profile,
            session_feedback=session_feedback,
            context_fusion=context_fusion,
        )
        default_rows: List[Dict[str, str]] = []
        for name in names:
            scheme = next((item for item in SCHEMES if str(item.get("name", "")).strip() == name), None)
            summary = ""
            if scheme is not None:
                lang = "hi" if (language or "").strip().lower() == "hi" else "en"
                summary = str(scheme.get(f"summary_{lang}") or scheme.get("summary_en") or "").strip()
            reason_suffix = _explain_reason(
                scheme or {},
                need_category=need_category,
                user_profile=user_profile,
            )
            default_rows.append({
                "scheme": name,
                "summary": summary,
                "reason": f"Recommended based on overall popularity and fit. {reason_suffix}",
            })
        _REASON_CACHE.set(reason_cache_key, list(default_rows))
        return default_rows

    ranked = _rank_schemes_cached(
        query,
        need_category=need_category,
        user_profile=user_profile,
        session_feedback=session_feedback,
        context_fusion=context_fusion,
    )
    ranked = _select_diverse_top(ranked, limit=max(limit, 3))

    response: List[Dict[str, str]] = []
    for _, scheme in ranked[:limit]:
        name = str(scheme.get("name", "")).strip()
        if not name:
            continue
        lang = "hi" if (language or "").strip().lower() == "hi" else "en"
        summary = str(scheme.get(f"summary_{lang}") or scheme.get("summary_en") or "").strip()
        reason = _explain_reason(
            scheme,
            need_category=need_category,
            user_profile=user_profile,
        )
        response.append({"scheme": name, "summary": summary, "reason": reason})
    _REASON_CACHE.set(reason_cache_key, list(response))
    return response
