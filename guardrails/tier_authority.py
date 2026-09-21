"""Guardrail: tier authority classification and governance.

Tier 1 (human only): the agent must never act autonomously.
Tier 2 (agent proposes, human approves): a recommendation is returned
but requires explicit user confirmation before the pipeline proceeds.
Tier 3 (agent acts autonomously): general climate queries, retrieval,
and chart generation.

Promotion between tiers is never automatic — it is tracked and logged
for human review only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import config

_TIER_1_PATTERNS = {
    "financial_recommendation": [
        r"should i (buy|purchase|invest in|sell)",
        r"is it worth (buying|investing)",
        r"financial (advice|recommendation)",
        r"insurance (premium|policy) (advice|recommendation)",
    ],
    "legal_advice": [
        r"am i liable",
        r"is my company liable",
        r"legal (advice|liability|obligation)",
        r"under (uk|us|indian|singapore) law",
        r"sue|lawsuit|litigation",
    ],
    "policy_commitment": [
        r"commit (the|our) (city|company|organisation|organization) to",
        r"binding policy (decision|commitment)",
    ],
}

_TIER_2_INTENTS = {
    "dataset_selection_high_stakes",
    "methodology_for_regulatory_submission",
}

_TIER_1_MESSAGE = (
    "This requires human expert review. The system cannot act "
    "autonomously on this."
)


@dataclass
class TierResult:
    """Result of tier authority classification.

    Attributes:
        tier: One of "tier_1", "tier_2", "tier_3".
        matched_category: The specific Tier 1/2 category matched, if any.
        message: User-facing message when the tier blocks/gates the query.
        requires_human_approval: True for Tier 2 (and always False-acting
            for Tier 1, which stops entirely rather than waiting).
    """

    tier: str
    matched_category: str | None = None
    message: str | None = None
    requires_human_approval: bool = False


def classify_tier(query: str, intent: str | None = None) -> TierResult:
    """Classifies a query into a governance tier.

    Args:
        query: The natural-language user query.
        intent: Optional pre-classified intent string, used to check
            against Tier 2 intent categories.

    Returns:
        A TierResult describing the assigned tier and any gating message.
    """
    lowered = query.lower()

    for category, patterns in _TIER_1_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lowered):
                return TierResult(
                    tier="tier_1",
                    matched_category=category,
                    message=_TIER_1_MESSAGE,
                    requires_human_approval=False,
                )

    if intent in _TIER_2_INTENTS:
        return TierResult(
            tier="tier_2",
            matched_category=intent,
            message=(
                "This recommendation requires your explicit confirmation "
                "before the system proceeds."
            ),
            requires_human_approval=True,
        )

    return TierResult(tier="tier_3")


def check_promotion_eligibility(error_rate: float, sustained_days: int) -> dict:
    """Checks whether a tier is eligible for promotion (e.g. Tier 2 ->
    Tier 3 autonomy) based on sustained low error rate. Never
    auto-promotes — only logs eligibility for a human to review.

    Args:
        error_rate: Observed error rate over the sustained window.
        sustained_days: Number of days the error rate has held.

    Returns:
        Dict with eligibility flag and the criteria checked, intended
        for logging only. A human must manually approve any promotion.
    """
    eligible = (
        error_rate <= config.TIER_ERROR_THRESHOLD
        and sustained_days >= config.TIER_SUSTAINED_DAYS
    )
    return {
        "eligible_for_promotion": eligible,
        "error_rate": error_rate,
        "error_rate_threshold": config.TIER_ERROR_THRESHOLD,
        "sustained_days": sustained_days,
        "sustained_days_required": config.TIER_SUSTAINED_DAYS,
        "action_required": "Human must manually review and approve promotion.",
    }
