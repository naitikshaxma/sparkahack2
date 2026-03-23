from backend.flow_engine import generate_response
from backend.intents import INTENT_APPLY_LOAN, INTENT_GENERAL_QUERY, normalize_intent_prediction


def test_valid_intent_normalizes_to_canonical() -> None:
    intent, confidence, fallback_used = normalize_intent_prediction("loan_application", 0.92)
    assert intent == INTENT_APPLY_LOAN
    assert confidence == 0.92
    assert fallback_used is False


def test_unknown_intent_is_handled_gracefully() -> None:
    intent, confidence, fallback_used = normalize_intent_prediction("totally_new_intent", 0.88)
    assert intent == INTENT_GENERAL_QUERY
    assert confidence == 0.88
    assert fallback_used is False


def test_low_confidence_intent_falls_back_to_general_query(monkeypatch) -> None:
    monkeypatch.setattr("backend.flow_engine.retrieve_scheme", lambda transcript, lang: None)
    monkeypatch.setattr(
        "backend.flow_engine.predict_intent_detailed",
        lambda transcript: {
            "raw_intent": INTENT_APPLY_LOAN,
            "primary_intent": INTENT_GENERAL_QUERY,
            "secondary_intents": [],
            "confidence": 0.1,
            "fallback_used": True,
            "source": "test",
        },
    )

    _, intent, confidence = generate_response(language="en", transcript="I need a loan")
    assert intent == INTENT_GENERAL_QUERY
    assert confidence == 0.1
