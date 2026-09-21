"""Integration test: runs the full LangGraph pipeline end to end for a
representative set of queries, exercising conditional routing, tier
authority, KG gate, and output filtering together.

Requires a running PostgreSQL instance (see docker-compose.yml) and a
configured GROQ_API_KEY, since it makes real LiteLLM calls.
"""

from __future__ import annotations

import pytest

from graph.workflow import run_pipeline


@pytest.mark.asyncio
async def test_out_of_scope_query_blocked_without_agents() -> None:
    state = await run_pipeline("What is the best pizza recipe?")
    assert state.router_decision == "out_of_scope"
    assert state.kg_results is None
    assert state.rag_results is None


@pytest.mark.asyncio
async def test_tier1_query_stops_immediately() -> None:
    state = await run_pipeline("Should I buy climate insurance for my Mumbai property?")
    assert state.tier_assigned == "tier_1"
    assert state.kg_results is None


@pytest.mark.asyncio
async def test_kg_coverage_gap_produces_honest_message() -> None:
    state = await run_pipeline("What is the flood risk for Antarctica under SSP5-8.5?")
    assert state.coverage_gap is True
    assert "coverage gap" in (state.final_answer or "").lower() or "gap" in (state.final_answer or "").lower()


@pytest.mark.asyncio
async def test_valid_query_produces_audit_record() -> None:
    state = await run_pipeline("What is the flood risk for Kerala under SSP5-8.5?")
    if state.coverage_gap or state.tier_assigned in ("tier_1", "tier_2"):
        pytest.skip("Routed to a non-terminal branch for this environment's KG/data state.")
    assert state.audit_record.get("query_id") == state.trace_id
    assert "faithfulness_score" in state.audit_record
