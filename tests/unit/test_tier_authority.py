"""Unit tests for guardrails/tier_authority.py."""

from __future__ import annotations

from guardrails.tier_authority import check_promotion_eligibility, classify_tier


def test_tier1_financial_recommendation_blocked() -> None:
    result = classify_tier("Should I buy climate insurance for my Mumbai property?")
    assert result.tier == "tier_1"
    assert result.matched_category == "financial_recommendation"


def test_tier1_legal_advice_blocked() -> None:
    result = classify_tier("Is my company liable for flood damage under UK law?")
    assert result.tier == "tier_1"
    assert result.matched_category == "legal_advice"


def test_tier2_requires_human_approval() -> None:
    result = classify_tier(
        "Which dataset should we use?", intent="dataset_selection_high_stakes"
    )
    assert result.tier == "tier_2"
    assert result.requires_human_approval is True


def test_tier3_general_query() -> None:
    result = classify_tier("What is the flood risk for Kerala under SSP5-8.5?")
    assert result.tier == "tier_3"


def test_promotion_eligibility_never_auto_promotes() -> None:
    result = check_promotion_eligibility(error_rate=0.01, sustained_days=31)
    assert result["eligible_for_promotion"] is True
    assert "Human must" in result["action_required"]


def test_promotion_eligibility_fails_below_sustained_days() -> None:
    result = check_promotion_eligibility(error_rate=0.01, sustained_days=5)
    assert result["eligible_for_promotion"] is False
