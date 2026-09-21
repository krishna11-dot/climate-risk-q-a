"""Dual-write audit logging: PostgreSQL AuditLog table (queryable) plus an
append-only JSONL backup (audit/queries.jsonl).

This is the backbone of "explainable to a regulator": every query's full
trail — tier, router decision, KG nodes traversed, datasets cited and
verified, RAG chunks used, faithfulness/groundedness scores, and cost —
is written here and never overwritten or deleted.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from db.connection import get_session
from db.models import AuditLog

logger = logging.getLogger(__name__)


async def write_audit_record(record: dict[str, Any]) -> None:
    """Writes one audit record to both PostgreSQL and the JSONL backup.

    Args:
        record: Dict containing at minimum query_id, timestamp,
            user_query, tier_assigned, router_decision, kg_nodes,
            datasets_cited, datasets_verified_in_kg, rag_chunks_used,
            analysis_code_run, guardrails_triggered, final_answer,
            faithfulness_score, groundedness_score, litellm_cost_usd,
            explainable_to_regulator, context_compacted.
    """
    record = {**record}
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    await _write_to_postgres(record)
    _append_to_jsonl(record)


async def _write_to_postgres(record: dict[str, Any]) -> None:
    """Inserts one row into the audit_log table.

    Args:
        record: The full audit record dict.
    """
    try:
        async with get_session() as session:
            audit_row = AuditLog(
                query_id=record.get("query_id", ""),
                user_query=record.get("user_query", ""),
                tier_assigned=record.get("tier_assigned"),
                router_decision=record.get("router_decision"),
                kg_nodes=record.get("kg_nodes_traversed") or record.get("kg_nodes"),
                datasets_cited=record.get("datasets_cited"),
                rag_chunks=record.get("rag_chunks_used") or record.get("rag_chunks"),
                final_answer=record.get("final_answer"),
                faithfulness=record.get("faithfulness_score"),
                groundedness=record.get("groundedness_score"),
                explainable=record.get("explainable_to_regulator"),
                compound_hazard=record.get("compound_hazard", False),
                region=record.get("region"),
            )
            session.add(audit_row)
            await session.commit()
    except Exception:  # noqa: BLE001 - audit writes must never crash the pipeline
        logger.exception("Failed to write audit record to PostgreSQL; JSONL backup retained.")


def _append_to_jsonl(record: dict[str, Any]) -> None:
    """Appends one audit record as a JSON line to the backup file.

    Args:
        record: The full audit record dict.
    """
    path = Path(config.AUDIT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


async def export_audit_report(query_id: str) -> dict[str, Any] | None:
    """Exports the full audit record for a single query, for regulatory
    review. Never overwrites or deletes source data.

    Args:
        query_id: The query identifier to look up.

    Returns:
        A formatted dict of the audit record, or None if not found.
    """
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.query_id == query_id)
        )
        row = result.scalar_one_or_none()

    if row is None:
        return None

    return {
        "query_id": row.query_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "user_query": row.user_query,
        "tier_assigned": row.tier_assigned,
        "router_decision": row.router_decision,
        "kg_nodes": row.kg_nodes,
        "datasets_cited": row.datasets_cited,
        "rag_chunks": row.rag_chunks,
        "final_answer": row.final_answer,
        "faithfulness": row.faithfulness,
        "groundedness": row.groundedness,
        "explainable": row.explainable,
        "compound_hazard": row.compound_hazard,
        "region": row.region,
    }


def export_regulatory_pdf(query_id: str) -> bytes:
    """Converts a JSON audit record into a formal PDF for regulatory
    filing.

    TODO: implement using reportlab once the base system is validated.
    Should render every field from export_audit_report() into a
    structured PDF document suitable for submission to a regulator.

    Args:
        query_id: The query identifier to export.

    Raises:
        NotImplementedError: Always, until implemented.
    """
    raise NotImplementedError(
        "TODO: regulatory PDF export not yet implemented. "
        "Use export_audit_report() for the JSON record in the meantime."
    )
