-- Migration: create climate_chunks and audit_log tables with pgvector.
-- Idempotent: safe to re-run via IF NOT EXISTS guards.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS climate_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    source_doc VARCHAR NOT NULL,
    section VARCHAR,
    page_number INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    ocr_extracted BOOLEAN NOT NULL DEFAULT FALSE,
    dataset VARCHAR,
    scenario VARCHAR,
    region VARCHAR,
    version VARCHAR,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS climate_chunks_source_page_chunk_idx
    ON climate_chunks (source_doc, page_number, chunk_index);

CREATE INDEX IF NOT EXISTS climate_chunks_embedding_idx
    ON climate_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS climate_chunks_dataset_idx ON climate_chunks (dataset);
CREATE INDEX IF NOT EXISTS climate_chunks_scenario_idx ON climate_chunks (scenario);
CREATE INDEX IF NOT EXISTS climate_chunks_region_idx ON climate_chunks (region);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_id VARCHAR NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_query TEXT NOT NULL,
    tier_assigned VARCHAR,
    router_decision VARCHAR,
    kg_nodes JSONB,
    datasets_cited JSONB,
    rag_chunks JSONB,
    final_answer TEXT,
    faithfulness FLOAT,
    groundedness FLOAT,
    explainable BOOLEAN,
    compound_hazard BOOLEAN NOT NULL DEFAULT FALSE,
    region VARCHAR
);

CREATE INDEX IF NOT EXISTS audit_log_query_id_idx ON audit_log (query_id);
CREATE INDEX IF NOT EXISTS audit_log_timestamp_idx ON audit_log (timestamp);
CREATE INDEX IF NOT EXISTS audit_log_region_idx ON audit_log (region);
