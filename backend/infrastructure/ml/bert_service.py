import logging
import pickle
from pathlib import Path
from typing import Optional, Tuple

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from backend.core.config import get_settings
from backend.core.intent_analytics import record_intent_event
from backend.application.use_cases.intent_resolver import resolve_intent_decision
from backend.intents import INTENT_APPLY_LOAN, INTENT_GENERAL_QUERY, INTENT_VERSION


logger = logging.getLogger(__name__)
SETTINGS = get_settings()

# Use env-configurable path and keep a legacy fallback path for compatibility.
MODEL_PATH = SETTINGS.model_path
LEGACY_MODEL_PATH = (Path(__file__).resolve().parents[1] / "models" / "intent_model").resolve()
HF_INTENT_MODEL_ID = SETTINGS.hf_intent_model_id

tokenizer: Optional[AutoTokenizer] = None
model: Optional[AutoModelForSequenceClassification] = None
label_encoder = None
_model_load_error: Optional[str] = None


def _resolve_model_dir() -> Optional[Path]:
    if MODEL_PATH.exists() and MODEL_PATH.is_dir():
        return MODEL_PATH
    if LEGACY_MODEL_PATH.exists() and LEGACY_MODEL_PATH.is_dir():
        return LEGACY_MODEL_PATH
    return None


def _load_intent_stack() -> None:
    global tokenizer, model, label_encoder, _model_load_error

    resolved_dir = _resolve_model_dir()

    try:
        if resolved_dir is not None:
            tokenizer = AutoTokenizer.from_pretrained(str(resolved_dir), local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(str(resolved_dir), local_files_only=True)
            model.eval()

            encoder_path = resolved_dir / "label_encoder.pkl"
            with open(encoder_path, "rb") as handle:
                label_encoder = pickle.load(handle)
            _model_load_error = None
            return

        # Optional remote model bootstrap when local model is not present.
        if HF_INTENT_MODEL_ID:
            tokenizer = AutoTokenizer.from_pretrained(HF_INTENT_MODEL_ID, local_files_only=False)
            model = AutoModelForSequenceClassification.from_pretrained(HF_INTENT_MODEL_ID, local_files_only=False)
            model.eval()

            # Label encoder is required for class-name mapping. Without it, use fallback.
            label_encoder = None
            _model_load_error = "label_encoder_missing_for_downloaded_model"
            logger.warning("Intent model loaded from HF but label encoder is missing, using fallback")
            return

        _model_load_error = "intent_model_not_found"
        logger.warning("Intent model failed to load, using fallback")
    except Exception as exc:
        tokenizer = None
        model = None
        label_encoder = None
        _model_load_error = str(exc)
        logger.exception("Intent model failed to load, using fallback")


def fallback_intent(text: str) -> Tuple[str, float]:
    lowered = (text or "").lower()
    if "loan" in lowered:
        return INTENT_APPLY_LOAN, 0.6
    return INTENT_GENERAL_QUERY, 0.5


_load_intent_stack()


def get_intent_model_status() -> dict:
    loaded = bool(model is not None and tokenizer is not None and label_encoder is not None)
    return {
        "model_path": str(MODEL_PATH),
        "legacy_model_path": str(LEGACY_MODEL_PATH),
        "loaded": loaded,
        "fallback_enabled": True,
        "error": _model_load_error,
        "num_labels": int(model.config.num_labels) if model is not None else 0,
        "label_count": int(len(label_encoder.classes_)) if label_encoder is not None else 0,
    }


def predict_intent_detailed(text: str, session_context: Optional[dict] = None) -> dict:
    clean_text = (text or "").strip()
    session_context = session_context or {}
    if not clean_text:
        decision = resolve_intent_decision(
            raw_intent=INTENT_GENERAL_QUERY,
            raw_confidence=0.0,
            text=clean_text,
            session_context=session_context,
        )
        decision.update(
            {
                "intent_version": INTENT_VERSION,
                "source": "empty_input",
                "raw_model_output": {"intent": INTENT_GENERAL_QUERY, "confidence": 0.0},
            }
        )
        record_intent_event(
            intent=decision["primary_intent"],
            confidence=decision["confidence"],
            fallback_used=decision["fallback_used"],
            low_confidence=decision["low_confidence"],
            raw_intent=decision["raw_intent"],
        )
        return decision

    if model is None or tokenizer is None or label_encoder is None:
        raw_intent, raw_confidence = fallback_intent(clean_text)
        decision = resolve_intent_decision(
            raw_intent=raw_intent,
            raw_confidence=raw_confidence,
            text=clean_text,
            session_context=session_context,
        )
        decision.update(
            {
                "intent_version": INTENT_VERSION,
                "source": "heuristic_fallback",
                "raw_model_output": {"intent": raw_intent, "confidence": raw_confidence},
            }
        )
        logger.info(
            "intent_detected intent=%s confidence=%.3f fallback_used=%s source=%s secondary_intents=%s",
            decision["primary_intent"],
            decision["confidence"],
            decision["fallback_used"],
            decision["source"],
            decision["secondary_intents"],
        )
        record_intent_event(
            intent=decision["primary_intent"],
            confidence=decision["confidence"],
            fallback_used=decision["fallback_used"],
            low_confidence=decision["low_confidence"],
            raw_intent=decision["raw_intent"],
        )
        return decision

    try:
        inputs = tokenizer(
            clean_text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=128,
        )

        with torch.no_grad():
            outputs = model(**inputs)

        probs = torch.softmax(outputs.logits, dim=1)
        idx = int(torch.argmax(probs, dim=1).item())
        raw_intent = str(label_encoder.classes_[idx])
        raw_confidence = float(probs[0][idx].item())
        top_k = min(3, probs.shape[1])
        top_vals, top_indices = torch.topk(probs[0], k=top_k)
        top_candidates = [
            {
                "intent": str(label_encoder.classes_[int(i.item())]),
                "confidence": float(v.item()),
            }
            for v, i in zip(top_vals, top_indices)
        ]

        decision = resolve_intent_decision(
            raw_intent=raw_intent,
            raw_confidence=raw_confidence,
            text=clean_text,
            session_context=session_context,
        )
        decision.update(
            {
                "intent_version": INTENT_VERSION,
                "source": "model",
                "raw_model_output": {
                    "intent": raw_intent,
                    "confidence": raw_confidence,
                    "top_candidates": top_candidates,
                },
            }
        )
        logger.info(
            "intent_detected intent=%s confidence=%.3f fallback_used=%s context_used=%s source=%s raw_intent=%s secondary_intents=%s",
            decision["primary_intent"],
            decision["confidence"],
            decision["fallback_used"],
            decision["context_used"],
            decision["source"],
            raw_intent,
            decision["secondary_intents"],
        )
        record_intent_event(
            intent=decision["primary_intent"],
            confidence=decision["confidence"],
            fallback_used=decision["fallback_used"],
            low_confidence=decision["low_confidence"],
            raw_intent=decision["raw_intent"],
        )
        return decision
    except Exception:
        logger.exception("Intent inference failed, using fallback")
        raw_intent, raw_confidence = fallback_intent(clean_text)
        decision = resolve_intent_decision(
            raw_intent=raw_intent,
            raw_confidence=raw_confidence,
            text=clean_text,
            session_context=session_context,
        )
        decision.update(
            {
                "intent_version": INTENT_VERSION,
                "source": "exception_fallback",
                "raw_model_output": {"intent": raw_intent, "confidence": raw_confidence},
            }
        )
        record_intent_event(
            intent=decision["primary_intent"],
            confidence=decision["confidence"],
            fallback_used=decision["fallback_used"],
            low_confidence=decision["low_confidence"],
            raw_intent=decision["raw_intent"],
        )
        return decision


def predict_intent(text: str) -> Tuple[str, float]:
    # Backward-compatible API retained for existing callers.
    decision = predict_intent_detailed(text=text, session_context=None)
    return decision["primary_intent"], float(decision["confidence"])
