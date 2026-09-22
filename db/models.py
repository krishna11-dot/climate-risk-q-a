"""SQLAlchemy ORM models for the climate risk chunk store and audit log.

ClimateChunk holds embedded, chunked document content with rich metadata
used for SQL pre-filtering (Stage 1 of the four-stage hybrid retrieval).
AuditLog holds one row per query, forming the queryable half of the
dual-write audit trail (the other half is the append-only JSONL backup).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import config


class Base(DeclarativeBase):
    """Declarative base for all ORM models in this project."""


class ClimateChunk(Base):
    """A single chunk of ingested climate document text with its embedding
    and metadata used for SQL pre-filtering and vector search.
    """

    __tablename__ = "climate_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(config.PGVECTOR_DIMS), nullable=False
    )
    source_doc: Mapped[str] = mapped_column(String, nullable=False)
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    ocr_extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    dataset: Mapped[str | None] = mapped_column(String, nullable=True)
    scenario: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AuditLog(Base):
    """One row per query: the full, queryable audit trail required to
    explain any system answer to a regulator on demand.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    tier_assigned: Mapped[str | None] = mapped_column(String, nullable=True)
    router_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    kg_nodes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    datasets_cited: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rag_chunks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    # True only for a real LLM-judged RAGAS faithfulness score; the online
    # per-query path currently always writes False, since `faithfulness`
    # is populated by a fast proxy there, not the real metric — see
    # agents/supervisor.py's audit_record comment for the full reasoning.
    faithfulness_measured: Mapped[bool] = mapped_column(Boolean, default=False)
    groundedness: Mapped[float | None] = mapped_column(Float, nullable=True)
    explainable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    compound_hazard: Mapped[bool] = mapped_column(Boolean, default=False)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
