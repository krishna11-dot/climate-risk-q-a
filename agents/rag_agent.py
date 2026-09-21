"""RAG agent: runs the four-stage hybrid retrieval pipeline.

Runs in PARALLEL with the KG agent, but consumes state.sql_filter which
the KG agent sets — the supervisor sequences the parallel gather so that
sql_filter is available by the time this agent's retrieval query fires.
Never hallucinates content: an empty candidate set returns an empty
result with a flag rather than fabricated text.
"""

from __future__ import annotations

from graph.state import ClimateRiskState
from observability.tracer import traceable
from rag.retriever import RetrievedChunk, retrieve


@traceable(name="rag_agent")
async def run_rag_agent(state: ClimateRiskState) -> ClimateRiskState:
    """Runs four-stage hybrid retrieval using state.sql_filter and
    populates state.rag_results.

    Args:
        state: Current pipeline state. Must have sql_filter populated
            by the KG agent for a meaningful (filtered) search; if
            absent, retrieval still runs unfiltered.

    Returns:
        Updated state with rag_results set to a list of chunk dicts,
        or an empty list with an explicit "no_results" flag chunk.
    """
    sql_filter = state.sql_filter or {"dataset": None, "scenario": None, "region": None}

    chunks: list[RetrievedChunk] = await retrieve(state.user_query, sql_filter)

    if not chunks:
        state.rag_results = []
        return state

    state.rag_results = [
        {
            "content": c.content,
            "source_doc": c.source_doc,
            "section": c.section,
            "page_number": c.page_number,
            "dataset": c.dataset,
            "scenario": c.scenario,
            "region": c.region,
            "ocr_extracted": c.ocr_extracted,
            "score": c.score,
        }
        for c in chunks
    ]
    return state
