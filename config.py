"""Central configuration for the Climate Risk Q&A multi-agent system.

Every model name, threshold, and tunable constant used anywhere in the
system lives here. No module outside this file should hardcode a model
name, threshold, or path. This makes the system auditable: a regulator
or reviewer can see the entire operating envelope of the agent stack by
reading one file.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# LLM MODELS (all routed through LiteLLM, never called directly via Groq SDK)
# ---------------------------------------------------------------------------

SUPERVISOR_MODEL: str = os.getenv("SUPERVISOR_MODEL", "groq/qwen/qwen3.8-27b")
RAG_AGENT_MODEL: str = os.getenv("RAG_AGENT_MODEL", "groq/openai/gpt-oss-20b")
KG_AGENT_MODEL: str = os.getenv("KG_AGENT_MODEL", "groq/openai/gpt-oss-20b")
ANALYSIS_AGENT_MODEL: str = os.getenv("ANALYSIS_AGENT_MODEL", "groq/qwen/qwen3.8-27b")

# ---------------------------------------------------------------------------
# LiteLLM gateway settings
# ---------------------------------------------------------------------------

LITELLM_CACHE_ENABLED: bool = os.getenv("LITELLM_CACHE_ENABLED", "true").lower() == "true"
LITELLM_FALLBACK_MODEL: str = os.getenv(
    "LITELLM_FALLBACK_MODEL", "openrouter/qwen/qwen3.6-72b"
)
LITELLM_MAX_RETRIES: int = int(os.getenv("LITELLM_MAX_RETRIES", "3"))

# ---------------------------------------------------------------------------
# Database / vector store
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/climate_risk",
)
PGVECTOR_DIMS: int = int(os.getenv("PGVECTOR_DIMS", "384"))
DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", "2"))
DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

# ---------------------------------------------------------------------------
# RAG / retrieval
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: str = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
TOP_K_RETRIEVAL: int = int(os.getenv("TOP_K_RETRIEVAL", "20"))
TOP_K_RERANKED: int = int(os.getenv("TOP_K_RERANKED", "5"))
RERANKER_MODEL: str = os.getenv(
    "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)
# ivfflat is an approximate-nearest-neighbor index: with the default
# probes=1 it only scans ~1/100th of the table before WHERE filters are
# applied, so a filtered ORDER BY ... LIMIT query can silently miss most
# genuinely matching rows. Raising probes trades a little query latency
# for correctness; 10 is a reasonable default for a lists=100 index.
IVFFLAT_PROBES: int = int(os.getenv("IVFFLAT_PROBES", "10"))

# ---------------------------------------------------------------------------
# Analysis agent
# ---------------------------------------------------------------------------

# Each run spawns a fresh subprocess for isolation, so this must cover
# cold interpreter startup + importing xarray/dask/cf_xarray/matplotlib
# (observed anywhere from ~15s to ~36s alone depending on system load)
# on top of the actual computation.
ANALYSIS_TIMEOUT: int = int(os.getenv("ANALYSIS_TIMEOUT", "90"))

# ---------------------------------------------------------------------------
# Evaluation / grounding thresholds
# ---------------------------------------------------------------------------

RAGAS_THRESHOLD: float = float(os.getenv("RAGAS_THRESHOLD", "0.80"))
GROUNDEDNESS_THRESHOLD: float = float(os.getenv("GROUNDEDNESS_THRESHOLD", "0.75"))
FAITHFULNESS_SEGMENT_THRESHOLD: float = float(
    os.getenv("FAITHFULNESS_SEGMENT_THRESHOLD", "0.80")
)

# ---------------------------------------------------------------------------
# Tier authority / governance
# ---------------------------------------------------------------------------

TIER_ERROR_THRESHOLD: float = float(os.getenv("TIER_ERROR_THRESHOLD", "0.02"))
TIER_SUSTAINED_DAYS: int = int(os.getenv("TIER_SUSTAINED_DAYS", "30"))

# ---------------------------------------------------------------------------
# Context management
# ---------------------------------------------------------------------------

CONTEXT_COMPACTION_THRESHOLD: float = float(
    os.getenv("CONTEXT_COMPACTION_THRESHOLD", "0.80")
)
MODEL_CONTEXT_LIMIT_TOKENS: int = int(os.getenv("MODEL_CONTEXT_LIMIT_TOKENS", "32000"))

# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------

AGENT_PAUSED: bool = os.getenv("AGENT_PAUSED", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Named alert owner / escalation path
# ---------------------------------------------------------------------------

ALERT_OWNER: dict[str, Any] = {
    # TODO: replace with a named human owner before production go-live.
    "name": "TODO: named human owner",
    "authority": "can set AGENT_PAUSED=True",
    "escalation_path": [
        "1. Set AGENT_PAUSED=True in config",
        "2. All queries -> human review",
        "3. Investigate LangSmith traces",
        "4. Fix + re-eval before restart",
    ],
}

# ---------------------------------------------------------------------------
# API keys / secrets (never hardcode values, always from environment)
# ---------------------------------------------------------------------------

GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
LITELLM_API_KEY: str | None = os.getenv("LITELLM_API_KEY", GROQ_API_KEY)
LANGSMITH_API_KEY: str | None = os.getenv("LANGSMITH_API_KEY")
LANGSMITH_PROJECT: str | None = os.getenv("LANGSMITH_PROJECT", "climate-risk-agent")
# Regional data residency endpoint (e.g. APAC: https://apac.api.smith.langchain.com).
# Defaults to the global/US endpoint if unset.
LANGSMITH_ENDPOINT: str | None = os.getenv("LANGSMITH_ENDPOINT")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

AUDIT_LOG_PATH: str = os.getenv("AUDIT_LOG_PATH", "audit/queries.jsonl")
TRACE_PATH: str = os.getenv("TRACE_PATH", "audit/traces/")

# TODO: configure UKCP18 PDF source directory before running rag/ingest.py
UKCP18_PDF_DIR: str = os.getenv("UKCP18_PDF_DIR", "data/ukcp18_pdfs/")

# TODO: configure CMIP6/CORDEX NetCDF file paths before running analysis_agent
CMIP6_NETCDF_DIR: str = os.getenv("CMIP6_NETCDF_DIR", "data/cmip6_netcdf/")
CORDEX_NETCDF_DIR: str = os.getenv("CORDEX_NETCDF_DIR", "data/cordex_netcdf/")

# ERA5 reanalysis data (Copernicus Climate Data Store, free with registration)
ERA5_NETCDF_DIR: str = os.getenv("ERA5_NETCDF_DIR", "data/era5_netcdf/")

KG_SCHEMA_PATH: str = os.getenv("KG_SCHEMA_PATH", "knowledge_graph/schema.json")
