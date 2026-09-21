"""KG agent: extracts hazard/region/scenario from natural language and
traverses the knowledge graph, applying the strict fallback order.

Runs in PARALLEL with the RAG agent. Sets state.sql_filter for the RAG
agent to consume.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

import config
from agents import call_llm
from graph.state import ClimateRiskState
from knowledge_graph.builder import load_schema
from knowledge_graph.query import KGLookupResult, lookup
from observability.tracer import traceable


class KGExtraction(BaseModel):
    """Structured extraction of hazard/region/scenario from a query."""

    hazard: str | None = None
    region: str | None = None
    scenario: str | None = None


_EXTRACTION_PROMPT = """You extract structured climate risk parameters from a
user question. Respond ONLY with a JSON object with keys "hazard",
"region", "scenario" — using values from these controlled vocabularies
if a value is mentioned or clearly implied, else null:

hazards: {hazards}
regions: {regions}
scenarios: {scenarios}

If no scenario is mentioned, default to "SSP5-8.5" (the standard high-
emissions reference case). User question: {query}
"""


def _fallback_regex_extract(query: str, schema: dict) -> KGExtraction:
    """Regex-based extraction fallback if the LLM response is unparsable.

    Args:
        query: The user query.
        schema: The loaded KG schema dict.

    Returns:
        Best-effort KGExtraction from direct keyword matching.
    """
    lowered = query.lower()
    hazard = next((h for h in schema["hazards"] if h in lowered), None)
    region = next(
        (r for r in schema["regions"] if r.lower().replace("_", " ") in lowered or r.lower() in lowered),
        None,
    )
    scenario = next((s for s in schema["scenarios"] if s.lower() in lowered), "SSP5-8.5")
    return KGExtraction(hazard=hazard, region=region, scenario=scenario)


async def _extract_parameters(query: str) -> tuple[KGExtraction, float]:
    """Extracts hazard/region/scenario via LLM, with a regex fallback.

    Args:
        query: The user's natural-language query.

    Returns:
        Tuple of (KGExtraction, litellm_cost_usd).
    """
    schema = load_schema()
    prompt = _EXTRACTION_PROMPT.format(
        hazards=schema["hazards"],
        regions=schema["regions"],
        scenarios=schema["scenarios"],
        query=query,
    )

    text, cost = await call_llm(
        model=config.KG_AGENT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return KGExtraction(**data), cost
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return _fallback_regex_extract(query, schema), cost


@traceable(name="kg_agent")
async def run_kg_agent(state: ClimateRiskState) -> ClimateRiskState:
    """Runs the KG agent: extract parameters, traverse the graph with
    fallback, and populate state.kg_results and state.sql_filter.

    Args:
        state: Current pipeline state.

    Returns:
        Updated state with kg_results, sql_filter, and coverage_gap set.
    """
    extraction, cost = await _extract_parameters(state.user_query)
    state.litellm_cost_usd += cost

    if not extraction.hazard or not extraction.region:
        state.coverage_gap = True
        state.kg_results = {
            "found": False,
            "coverage_gap": True,
            "reason": "Could not extract hazard/region from query.",
        }
        return state

    scenario = extraction.scenario or "SSP5-8.5"
    result: KGLookupResult = lookup(extraction.hazard, extraction.region, scenario)

    state.kg_results = {
        "found": result.found,
        "hazard": result.hazard,
        "variable": result.variable,
        "scenario": result.scenario,
        "region": result.region,
        "parent_region": result.parent_region,
        "dataset": result.dataset,
        "fallback_used": result.fallback_used,
        "coverage_gap": result.coverage_gap,
        "nodes_traversed": result.nodes_traversed,
    }
    state.coverage_gap = result.coverage_gap

    if result.found:
        regions = [r for r in [result.region, result.parent_region] if r]
        state.sql_filter = {
            "dataset": result.dataset,
            "scenario": result.scenario,
            "region": regions,
        }

    return state
