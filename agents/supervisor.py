"""Supervisor agent: conditional routing, tier authority gating, parallel
RAG+KG execution, analysis sequencing, result combination, and context
management.

This is the orchestration entrypoint invoked by graph/workflow.py.
"""

from __future__ import annotations

import asyncio
import re
import uuid

import config
from agents import call_llm
from agents.analysis_agent import run_analysis_agent
from agents.kg_agent import run_kg_agent
from agents.rag_agent import run_rag_agent
from graph.state import ClimateRiskState
from guardrails.input_validator import validate_input
from guardrails.kg_gate import check_kg_gate
from guardrails.output_filter import apply_output_filter
from guardrails.tier_authority import classify_tier
from knowledge_graph.builder import load_schema
from knowledge_graph.query import KGLookupResult
from observability.tracer import traceable

_PURE_CALCULATION_PATTERNS = [
    r"^\s*what is \d",
    r"^\s*\d+[\s+\-*/]+\d+",
    r"convert \d+.*to",
]

_AMBIGUOUS_MIN_KEYWORDS = 1


def conditional_router(query: str, validation_is_out_of_scope: bool) -> str:
    """Step 0: decides whether the query needs retrieval at all.

    Args:
        query: The (validated) user query.
        validation_is_out_of_scope: Whether input_validator already
            flagged the query as out of scope.

    Returns:
        One of "direct_llm", "out_of_scope", "needs_retrieval".
    """
    if validation_is_out_of_scope:
        return "out_of_scope"

    lowered = query.lower()
    if any(re.search(pattern, lowered) for pattern in _PURE_CALCULATION_PATTERNS):
        return "direct_llm"

    return "needs_retrieval"


def _is_ambiguous(query: str) -> bool:
    """Heuristic ambiguity check: a query with no hazard/region keyword
    at all is treated as ambiguous and routed to clarification.

    Args:
        query: The user query.

    Returns:
        True if the query lacks any recognisable hazard or region term.
    """
    schema = load_schema()
    lowered = query.lower()
    has_hazard = any(h in lowered for h in schema["hazards"])
    has_region = any(r.lower().replace("_", " ") in lowered for r in schema["regions"])
    return not (has_hazard or has_region)


def _estimate_tokens(text: str) -> int:
    """Rough whitespace-based token estimate for context tracking."""
    return len(text.split())


def _maybe_compact_context(state: ClimateRiskState) -> None:
    """Applies context compaction if usage exceeds the configured
    threshold of the model's context limit: summarises completed steps
    and clears intermediate results.

    Args:
        state: Current pipeline state, mutated in place.
    """
    limit = config.MODEL_CONTEXT_LIMIT_TOKENS
    if state.context_size_tokens > config.CONTEXT_COMPACTION_THRESHOLD * limit:
        # Clear bulky intermediate payloads; keep only what downstream
        # steps and the audit trail need.
        if state.rag_results:
            state.rag_results = state.rag_results[: config.TOP_K_RERANKED]
        state.context_compacted = True
        state.context_size_tokens = _estimate_tokens(state.user_query)


async def _run_direct_llm(state: ClimateRiskState) -> ClimateRiskState:
    """Handles the direct_llm router branch: answers without retrieval.

    Args:
        state: Current pipeline state.

    Returns:
        Updated state with final_answer set, no agents/guardrails involved
        beyond input validation.
    """
    answer, cost, llm_unavailable = await call_llm(
        model=config.SUPERVISOR_MODEL,
        messages=[{"role": "user", "content": state.user_query}],
        # Groq's free tier enforces a hard ~1000 output-token cap per
        # request for this model; staying under it avoids a RateLimitError.
        max_tokens=900,
    )
    state.litellm_cost_usd += cost
    state.llm_unavailable = llm_unavailable
    state.final_answer = answer
    # A total LLM failure isn't "nothing to ground" — it's zero content
    # produced at all. Scoring it 1.0 would misreport an outage as a
    # perfect answer in the audit trail.
    state.groundedness_score = 0.0 if llm_unavailable else 1.0
    return state


async def _combine_results(state: ClimateRiskState) -> str:
    """Combines RAG chunks, KG traversal, and analysis results into one
    grounded draft answer via the supervisor LLM.

    Args:
        state: Pipeline state with rag_results, kg_results, and
            analysis_results populated.

    Returns:
        Draft answer text (pre output-filter).
    """
    context_parts = []
    if state.rag_results:
        context_parts.append(
            "Retrieved evidence:\n"
            + "\n---\n".join(c["content"] for c in state.rag_results)
        )
    if state.kg_results:
        context_parts.append(f"Knowledge graph result: {state.kg_results}")
    if state.analysis_results:
        context_parts.append(f"Quantitative analysis: {state.analysis_results}")

    context_text = "\n\n".join(context_parts)
    state.context_size_tokens += _estimate_tokens(context_text)
    _maybe_compact_context(state)

    prompt = (
        "Answer the user's climate risk question using ONLY the evidence "
        "below. Cite dataset names exactly as given. If evidence is "
        "insufficient, say so. Keep your reasoning brief and go straight "
        "to a concise answer — you have a limited output budget.\n\n"
        f"Question: {state.user_query}\n\n{context_text}"
    )

    answer, cost, llm_unavailable = await call_llm(
        model=config.SUPERVISOR_MODEL,
        messages=[{"role": "user", "content": prompt}],
        # SUPERVISOR_MODEL is a reasoning model that emits a visible
        # <think> block (stripped in call_llm) before its answer, so this
        # needs headroom for both — but Groq's free tier caps output at
        # ~1000 tokens/request for this model, so 900 is as high as we
        # can safely go without triggering a RateLimitError.
        max_tokens=900,
    )
    state.litellm_cost_usd += cost
    state.llm_unavailable = state.llm_unavailable or llm_unavailable
    return answer


def _estimate_faithfulness(state: ClimateRiskState) -> float:
    """Estimates a faithfulness/groundedness score for the draft answer.

    A full RAGAS faithfulness call is available offline via
    evaluation/generate_eval_records.py + evaluation/score_eval_records.py
    (the latter runs in the isolated .venv-ragas); for the online
    per-query path this uses a
    fast proxy — presence of grounded evidence — to avoid adding a
    second LLM round-trip on every request while still enforcing the
    threshold honestly (no retrieved evidence => low score).

    Args:
        state: Pipeline state after retrieval/KG/analysis have run.

    Returns:
        A score in [0, 1].
    """
    if state.llm_unavailable:
        # Evidence may well have been retrieved, but the LLM that would
        # have turned it into an answer never ran — scoring this on
        # evidence presence alone would call a total outage "grounded."
        return 0.0
    has_rag = bool(state.rag_results)
    has_kg = bool(state.kg_results and state.kg_results.get("found"))
    has_analysis = bool(state.analysis_results and state.analysis_results.get("success"))

    if not has_rag and not has_kg:
        return 0.0
    score = 0.5
    if has_rag:
        score += 0.3
    if has_kg:
        score += 0.15
    if has_analysis:
        score += 0.05
    return min(score, 1.0)


@traceable(name="supervisor")
async def run_supervisor(state: ClimateRiskState) -> ClimateRiskState:
    """Runs the full supervisor pipeline: input validation, conditional
    routing, tier authority, parallel RAG+KG, sequenced analysis, result
    combination, and output filtering.

    Args:
        state: Initial state with only user_query populated.

    Returns:
        Fully populated final state, including final_answer and
        audit_record.
    """
    state.trace_id = state.trace_id or str(uuid.uuid4())

    validation = validate_input(state.user_query)
    if not validation.is_valid:
        state.router_decision = "out_of_scope" if validation.is_out_of_scope else "blocked"
        state.final_answer = validation.blocked_reason
        return state

    query_for_pipeline = validation.redacted_query

    # STEP 0: conditional router.
    router_decision = conditional_router(query_for_pipeline, validation.is_out_of_scope)
    state.router_decision = router_decision

    if router_decision == "out_of_scope":
        state.final_answer = "This query is out of scope for climate risk analysis."
        return state

    if router_decision == "direct_llm":
        return await _run_direct_llm(state)

    # STEP 1: tier authority check.
    tier_result = classify_tier(query_for_pipeline, intent=state.intent)
    state.tier_assigned = tier_result.tier

    if tier_result.tier == "tier_1":
        state.final_answer = tier_result.message
        return state

    if tier_result.tier == "tier_2":
        state.human_approval_required = True
        state.final_answer = tier_result.message
        return state

    if _is_ambiguous(query_for_pipeline):
        state.clarification_needed = True
        state.final_answer = (
            "Your question is too broad to answer precisely. Could you "
            "specify a hazard (flood/heat/drought), a region, and a "
            "climate scenario if you have one in mind?"
        )
        return state

    # STEP 2: parallel execution. The KG agent's sql_filter must be
    # available before the RAG agent's retrieval query fires, so KG runs
    # first, then RAG and analysis proceed together off its result.
    state = await run_kg_agent(state)

    kg_gate = check_kg_gate(KGLookupResult(**{
        k: state.kg_results.get(k, [] if k == "nodes_traversed" else None)
        for k in ("found", "hazard", "variable", "scenario", "region",
                  "parent_region", "dataset", "fallback_used", "coverage_gap",
                  "nodes_traversed")
    })) if state.kg_results else None

    if kg_gate is not None and not kg_gate.passed:
        state.final_answer = kg_gate.user_message
        return state

    # Each concurrent branch gets its OWN deep copy. Both agents mutate the
    # state object they are handed, so handing them the same instance makes
    # them write over each other and share one cost accumulator — which
    # then has to be un-double-counted with a lossy max(). Copying keeps
    # each branch's spend separate so the totals below can simply be summed.
    cost_before = state.litellm_cost_usd
    rag_task = asyncio.create_task(run_rag_agent(state.model_copy(deep=True)))

    if state.kg_results and state.kg_results.get("found"):
        analysis_task = asyncio.create_task(
            run_analysis_agent(state.model_copy(deep=True))
        )
        rag_state, analysis_state = await asyncio.gather(rag_task, analysis_task)
        state.rag_results = rag_state.rag_results
        state.analysis_results = analysis_state.analysis_results
        rag_spend = rag_state.litellm_cost_usd - cost_before
        analysis_spend = analysis_state.litellm_cost_usd - cost_before
        state.litellm_cost_usd = cost_before + rag_spend + analysis_spend
        state.llm_unavailable = (
            state.llm_unavailable
            or rag_state.llm_unavailable
            or analysis_state.llm_unavailable
        )
    else:
        rag_state = await rag_task
        state.rag_results = rag_state.rag_results
        state.llm_unavailable = state.llm_unavailable or rag_state.llm_unavailable
        state.litellm_cost_usd = rag_state.litellm_cost_usd

    # STEP 3: combine results.
    draft_answer = await _combine_results(state)
    faithfulness = _estimate_faithfulness(state)
    state.groundedness_score = faithfulness

    schema = load_schema()
    filter_result = apply_output_filter(draft_answer, faithfulness, schema["datasets"])
    state.final_answer = filter_result.final_answer

    state.audit_record = {
        "query_id": state.trace_id,
        "user_query": state.user_query,
        "tier_assigned": state.tier_assigned,
        "router_decision": state.router_decision,
        "kg_nodes_traversed": state.kg_results.get("nodes_traversed") if state.kg_results else None,
        "datasets_cited": list(filter_result.datasets_verified.keys()),
        "datasets_verified_in_kg": filter_result.datasets_verified,
        "rag_chunks_used": state.rag_results,
        "analysis_code_run": (state.analysis_results or {}).get("code_used"),
        "guardrails_triggered": [
            r for r in [filter_result.blocked_reason] if r
        ],
        "final_answer": state.final_answer,
        # "faithfulness_score" is fed to the DB's `faithfulness` column
        # (see observability/audit_logger.py), which evaluation/
        # online_monitor.py's drift detection depends on being populated —
        # so it can't simply be left null. But this number comes from
        # _estimate_faithfulness()'s fast proxy (presence of grounded
        # evidence), not the real LLM-judged RAGAS faithfulness metric
        # computed offline in evaluation/score_eval_records.py. This flag
        # makes that distinction explicit on every record, so a regulator
        # (or anyone reading one via export_audit_report) doesn't mistake
        # it for a measured quantity.
        "faithfulness_score": faithfulness,
        "faithfulness_measured": False,
        "groundedness_score": faithfulness,
        "litellm_cost_usd": state.litellm_cost_usd,
        "explainable_to_regulator": True,
        "context_compacted": state.context_compacted,
        "region": state.kg_results.get("region") if state.kg_results else None,
        # Distinct from coverage_gap: this means the LLM layer itself was
        # down (both primary and fallback model calls failed), not that
        # the system correctly found no evidence. See graph/state.py's
        # llm_unavailable docstring and MAINTENANCE.md for why conflating
        # the two with a normal refusal hides real outages from
        # monitoring — evaluation/online_monitor.py alerts on this
        # immediately, unlike the faithfulness-drift check which averages
        # over a window.
        "llm_unavailable": state.llm_unavailable,
    }

    # TODO (future iteration - compound hazard): detect queries like
    # "flood AND heat risk for Mumbai" and run run_kg_agent twice via
    # asyncio.gather() — once per hazard — then have the analysis agent
    # compute both metrics and combine them. Insurance firms ask this way.

    return state
