"""LangGraph workflow definition wiring the supervisor as the orchestrating
node. The supervisor internally handles conditional routing, tier
authority, and parallel RAG/KG/analysis execution; the graph here exposes
a single entrypoint node so LangGraph's run/observability machinery wraps
the whole pipeline.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.supervisor import run_supervisor
from graph.state import ClimateRiskState


def build_workflow() -> StateGraph:
    """Builds the LangGraph StateGraph for the climate risk pipeline.

    Returns:
        A compiled LangGraph graph with a single "supervisor" node.
    """
    graph = StateGraph(ClimateRiskState)
    graph.add_node("supervisor", run_supervisor)
    graph.set_entry_point("supervisor")
    graph.add_edge("supervisor", END)
    return graph.compile()


_WORKFLOW = None


def get_workflow():
    """Returns a process-wide cached compiled workflow instance."""
    global _WORKFLOW
    if _WORKFLOW is None:
        _WORKFLOW = build_workflow()
    return _WORKFLOW


async def run_pipeline(user_query: str) -> ClimateRiskState:
    """Runs the full pipeline for a single user query.

    Args:
        user_query: The raw natural-language question.

    Returns:
        The final ClimateRiskState after the pipeline completes.
    """
    workflow = get_workflow()
    initial_state = ClimateRiskState(user_query=user_query)
    result = await workflow.ainvoke(initial_state)
    if isinstance(result, dict):
        return ClimateRiskState(**result)
    return result
