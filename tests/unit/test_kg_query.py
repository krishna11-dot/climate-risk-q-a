"""Unit tests for knowledge_graph/query.py: exact match, parent region
fallback, adjacent scenario fallback, and hard-stop coverage gaps.
"""

from __future__ import annotations

from knowledge_graph.query import lookup, verify_dataset_in_kg


def test_exact_match_resolves_dataset() -> None:
    result = lookup("flood", "Kerala", "SSP5-8.5")
    assert result.found is True
    assert result.fallback_used == "exact"
    assert result.dataset == "ERA5"


def test_parent_region_fallback() -> None:
    # UK has no heat+SSP1-2.6 combination of its own (only SSP2-4.5 and
    # SSP5-8.5), so this must climb to UK's parent, Global, which does
    # have one. Asserting the exact fallback tier and resolved region
    # (not just "found is True") is the point: a prior version of this
    # test accepted either "exact" or "parent_region", which passed
    # regardless of whether the fallback logic ran at all.
    result = lookup("heat", "UK", "SSP1-2.6")
    assert result.found is True
    assert result.fallback_used == "parent_region"
    assert result.region == "Global"
    assert result.dataset == "ERA5"


def test_adjacent_scenario_fallback() -> None:
    result = lookup("flood", "Mumbai", "SSP3-7.0")
    assert result.found is True
    assert result.fallback_used == "adjacent_scenario"
    assert result.scenario == "SSP2-4.5"


def test_hard_stop_coverage_gap() -> None:
    result = lookup("flood", "Antarctica", "SSP5-8.5")
    assert result.found is False
    assert result.coverage_gap is True


def test_verify_dataset_in_kg() -> None:
    assert verify_dataset_in_kg("CMIP6") is True
    assert verify_dataset_in_kg("SuperClimate9000") is False
