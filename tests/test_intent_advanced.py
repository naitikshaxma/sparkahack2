from backend.intent_analytics import get_intent_metrics, record_intent_event
from backend.intent_resolution import detect_multi_intents, resolve_intent_decision
from backend.intents import INTENT_APPLY_LOAN, calibrate_confidence


def test_multi_intent_detection_returns_multiple_candidates() -> None:
    intents = detect_multi_intents("I want to apply for a loan and check application status")
    assert INTENT_APPLY_LOAN in intents
    assert "check_application_status" in intents


def test_context_aware_correction_uses_last_intent() -> None:
    decision = resolve_intent_decision(
        raw_intent="general_query",
        raw_confidence=0.1,
        text="hmm",
        session_context={"last_intent": INTENT_APPLY_LOAN, "last_action": "apply"},
    )
    assert decision["primary_intent"] == INTENT_APPLY_LOAN
    assert decision["context_used"] is True


def test_calibrate_confidence_applies_keyword_boost() -> None:
    calibrated, boost_used = calibrate_confidence(0.30, INTENT_APPLY_LOAN, "please start application for loan")
    assert boost_used is True
    assert calibrated > 0.30


def test_intent_analytics_tracking_updates_counters() -> None:
    before = get_intent_metrics()
    before_freq = int(before.get("intent_frequency", {}).get(INTENT_APPLY_LOAN, 0))
    before_fallback = int(before.get("fallback_frequency", 0))

    record_intent_event(
        intent=INTENT_APPLY_LOAN,
        confidence=0.25,
        fallback_used=True,
        low_confidence=True,
        raw_intent="unknown",
    )

    after = get_intent_metrics()
    after_freq = int(after.get("intent_frequency", {}).get(INTENT_APPLY_LOAN, 0))
    after_fallback = int(after.get("fallback_frequency", 0))

    assert after_freq >= before_freq + 1
    assert after_fallback >= before_fallback + 1
