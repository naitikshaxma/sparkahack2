import math

import pytest

from backend.application.engines import decision as decision_engine
from backend.application.engines import eligibility as eligibility_engine
from backend.infrastructure.ml import rag_service
from backend.utils import form_schema


def test_dynamic_weights_are_bounded_and_normalized():
    weights = rag_service._dynamic_scoring_weights(
        query="loan support",
        confidence=0.15,
        profile_completeness=0.9,
    )

    assert set(weights.keys()) == {"embedding", "keyword", "category", "eligibility"}
    assert math.isclose(sum(weights.values()), 1.0, rel_tol=1e-6)
    for value in weights.values():
        assert rag_service.MIN_SCORING_WEIGHT <= value <= rag_service.MAX_SCORING_WEIGHT


def test_diversity_keeps_top1_and_prefers_category_variety():
    ranked = [
        (95, {"name": "Top Housing Plan", "category": "housing", "keywords": ["house", "home"]}),
        (92, {"name": "Top Housing Plan Plus", "category": "housing", "keywords": ["house", "home"]}),
        (90, {"name": "Health Cover Plan", "category": "health", "keywords": ["health", "hospital"]}),
        (88, {"name": "Finance Loan Plan", "category": "financial", "keywords": ["loan", "credit"]}),
    ]

    selected = rag_service._select_diverse_top(ranked, limit=3)
    selected_names = [item[1]["name"] for item in selected]
    selected_categories = [item[1].get("category") for item in selected]

    assert selected_names[0] == "Top Housing Plan"
    assert len(selected) == 3
    assert len(set(selected_categories[:3])) >= 2


def test_rank_schemes_excludes_strongly_ineligible(monkeypatch):
    scheme_a = {"name": "A", "category": "financial"}
    scheme_b = {"name": "B", "category": "health"}
    monkeypatch.setattr(rag_service, "PREPARED_SCHEMES", [(scheme_a, ["a"]), (scheme_b, ["b"])])
    monkeypatch.setattr(rag_service, "SCHEME_BLOBS", [(scheme_a, "a"), (scheme_b, "b")])

    def fake_eligibility(_profile, scheme):
        if scheme.get("name") == "B":
            return {"eligible": False, "score": 0.05, "reason": "too low"}
        return {"eligible": True, "score": 0.8, "reason": "ok"}

    monkeypatch.setattr(rag_service, "check_eligibility", fake_eligibility)
    monkeypatch.setattr(rag_service, "_score_scheme_match", lambda *args, **kwargs: 70)

    ranked = rag_service._rank_schemes("help", need_category="financial", user_profile={"user_type": "general"})
    names = [item[1]["name"] for item in ranked]

    assert names == ["A"]


def test_detect_user_need_category_and_confidence():
    result = decision_engine.detect_user_need("Mujhe hospital treatment aur health scheme chahiye")

    assert result["category"] == "health"
    assert 0.0 <= float(result["confidence"]) <= 1.0
    assert isinstance(result["reasoning"], str)


def test_eligibility_handles_missing_data_edge_cases():
    scheme = {"target_user": "farmer", "income_limit": 300000}

    output_missing_profile = eligibility_engine.check_eligibility({}, scheme)
    output_high_income = eligibility_engine.check_eligibility(
        {"user_type": "farmer", "annual_income": "900000"},
        scheme,
    )

    assert set(output_missing_profile.keys()) == {"eligible", "score", "reason"}
    assert 0.0 <= float(output_missing_profile["score"]) <= 1.0
    assert output_high_income["eligible"] is True or output_high_income["eligible"] is False
    assert "Income" in output_high_income["reason"] or "income" in output_high_income["reason"]


def test_form_schema_validation_and_field_progression():
    assert form_schema.resolve_scheme_name("PM KISAN Yojana") == "pm kisan"

    valid_phone = form_schema.validate_field("phone", "9876543210", language="en")
    invalid_phone = form_schema.validate_field("phone", "111", language="en")

    assert valid_phone["valid"] is True
    assert invalid_phone["valid"] is False
    assert invalid_phone["error_code"] == "invalid_phone"

    session = {
        "selected_scheme": "loan assistance",
        "field_completion": {
            "full_name": True,
            "phone": False,
            "aadhaar_number": False,
            "annual_income": False,
        },
    }
    assert form_schema.get_next_field(session) == "phone"
