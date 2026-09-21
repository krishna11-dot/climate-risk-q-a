"""Shared LangGraph state schema for the climate risk agent pipeline.

Every agent node reads from and writes to this single Pydantic v2 model.
Using a structured schema (rather than a free-form dict) is one of the
four anti-hallucination techniques: agents cannot invent new fields or
silently pass malformed data between nodes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClimateRiskState(BaseModel):
    """Full state object threaded through the LangGraph workflow.

    Attributes:
        user_query: The raw natural-language question from the user.
        router_decision: Output of the conditional router
            ("direct_llm", "out_of_scope", "needs_retrieval").
        tier_assigned: Governance tier ("tier_1", "tier_2", "tier_3").
        intent: Classified intent of the query (e.g. "general_climate_query").
        sql_filter: Filter dict derived from the KG result, used to
            pre-filter candidate chunks before vector search.
        rag_results: Top reranked chunks returned by the RAG agent.
        kg_results: Result of the knowledge graph traversal.
        analysis_results: Output of the analysis agent (value, range, chart).
        coverage_gap: True if the KG has no path for the requested
            hazard/region/scenario combination, even after fallback.
        clarification_needed: True if the query is too ambiguous to route.
        human_approval_required: True if a Tier 2 query needs explicit
            user confirmation before the pipeline proceeds.
        groundedness_score: Faithfulness/groundedness score of the answer.
        final_answer: The final natural-language answer returned to the user.
        audit_record: Full audit trail dict for this query.
        trace_id: LangSmith trace identifier for this run.
        error: Error message, if any step failed.
        context_size_tokens: Running token count of accumulated context.
        context_compacted: True if context was summarised/cleared mid-run.
        litellm_cost_usd: Cumulative LiteLLM-reported cost for this query.
    """

    user_query: str
    router_decision: str | None = None
    tier_assigned: str | None = None
    intent: str | None = None
    sql_filter: dict[str, Any] | None = None
    rag_results: list[dict[str, Any]] | None = None
    kg_results: dict[str, Any] | None = None
    analysis_results: dict[str, Any] | None = None
    coverage_gap: bool = False
    clarification_needed: bool = False
    human_approval_required: bool = False
    groundedness_score: float | None = None
    final_answer: str | None = None
    audit_record: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = ""
    error: str | None = None
    context_size_tokens: int = 0
    context_compacted: bool = False
    litellm_cost_usd: float = 0.0
