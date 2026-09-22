"""Unit tests for db/models.py and db/connection.py structure, without
requiring a live PostgreSQL instance.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from db.connection import get_engine, get_session_factory
from db.models import AuditLog, ClimateChunk


def test_climate_chunk_table_columns() -> None:
    columns = {c.name for c in ClimateChunk.__table__.columns}
    expected = {
        "id", "content", "embedding", "source_doc", "section",
        "page_number", "chunk_index", "ocr_extracted", "dataset",
        "scenario", "region", "version", "ingested_at",
    }
    assert expected.issubset(columns)


def test_audit_log_table_columns() -> None:
    columns = {c.name for c in AuditLog.__table__.columns}
    expected = {
        "id", "query_id", "timestamp", "user_query", "tier_assigned",
        "router_decision", "kg_nodes", "datasets_cited", "rag_chunks",
        "final_answer", "faithfulness", "faithfulness_measured",
        "groundedness", "explainable", "compound_hazard",
    }
    assert expected.issubset(columns)


def test_climate_chunk_has_dedup_key_columns() -> None:
    # The unique constraint itself is defined at the migration SQL level
    # (db/migrations/001_create_chunks_table.sql), not on the SQLAlchemy
    # model, so it can't be verified from here without a live database —
    # this only checks that the three columns it's built from exist on
    # the model. A prior version of this test computed
    # `ClimateChunk.__table__.indexes` and never used the result, which
    # made it look like it verified the constraint when it didn't.
    assert {"source_doc", "page_number", "chunk_index"}.issubset(
        {c.name for c in ClimateChunk.__table__.columns}
    )


def test_get_engine_returns_async_engine() -> None:
    engine = get_engine()
    assert isinstance(engine, AsyncEngine)


def test_session_factory_is_singleton() -> None:
    factory_one = get_session_factory()
    factory_two = get_session_factory()
    assert factory_one is factory_two
