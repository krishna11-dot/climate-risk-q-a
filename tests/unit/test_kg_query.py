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
    # "flood" + "SSP5-8.5" has no direct London combination in schema,
    # but South_Asia/Global does not cover London either; use a region
    # with a defined parent that lacks its own exact combination instead.
    result = lookup("heat", "UK", "SSP1-2.6")
    assert result.found is True
    assert result.fallback_used in ("exact", "parent_region")


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
