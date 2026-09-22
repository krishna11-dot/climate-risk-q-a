"""FastAPI application entrypoint: exposes POST /query, honors the global
kill switch (AGENT_PAUSED), and initializes LangSmith tracing on startup.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

import config
from db.connection import dispose_engine
from graph.workflow import run_pipeline
from observability.audit_logger import export_audit_report, write_audit_record
from observability.tracer import configure_langsmith


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    query: str


def is_agent_paused() -> bool:
    """Reads the kill switch live, on every call.

    Deliberately not cached in a module-level constant: the documented
    escalation path in config.ALERT_OWNER is "set AGENT_PAUSED=True",
    and an operator doing that during an incident must take effect
    immediately, not at the next process restart.

    Returns:
        True if all inference should be paused and routed to human review.
    """
    return config.AGENT_PAUSED


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: configure tracing on startup, dispose the
    database connection pool on shutdown.
    """
    configure_langsmith()
    yield
    await dispose_engine()


app = FastAPI(title="Climate Risk Q&A Agent", lifespan=lifespan)


@app.post("/query")
async def query(request: QueryRequest) -> dict:
    """Runs the climate risk pipeline for a single query, unless the
    global kill switch is engaged.

    Args:
        request: The incoming query request.

    Returns:
        The pipeline result as a dict, or a paused-system response.
    """
    if is_agent_paused():
        return {
            "status": "paused",
            "message": "System under review. Please contact your climate specialist.",
            "human_review": True,
        }

    state = await run_pipeline(request.query)

    if state.audit_record:
        await write_audit_record(state.audit_record)

    return {
        "status": "ok",
        "final_answer": state.final_answer,
        "tier_assigned": state.tier_assigned,
        "router_decision": state.router_decision,
        "kg_results": state.kg_results,
        "rag_results": state.rag_results,
        "analysis_results": state.analysis_results,
        "coverage_gap": state.coverage_gap,
        "clarification_needed": state.clarification_needed,
        "human_approval_required": state.human_approval_required,
        "groundedness_score": state.groundedness_score,
        "litellm_cost_usd": state.litellm_cost_usd,
        "trace_id": state.trace_id,
    }


@app.get("/audit/{query_id}")
async def get_audit_record(query_id: str) -> dict:
    """Returns the full audit record for a given query id, for
    regulatory review.

    Args:
        query_id: The trace/query identifier.

    Returns:
        The formatted audit record dict, or a not-found message.
    """
    record = await export_audit_report(query_id)
    if record is None:
        return {"status": "not_found", "query_id": query_id}
    return {"status": "ok", "record": record}


@app.get("/health")
async def health() -> dict:
    """Basic liveness check."""
    return {"status": "ok", "agent_paused": is_agent_paused()}
