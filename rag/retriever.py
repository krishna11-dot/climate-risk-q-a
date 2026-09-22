"""Four-stage hybrid retrieval: SQL pre-filter -> pgvector semantic search
-> BM25 keyword search -> cross-encoder reranking.

The SQL pre-filter always runs first and is driven by the KG agent's
sql_filter (dataset/scenario/region), narrowing the search space by
roughly 50x before any embedding math happens. This is what makes
"zero hallucinated dataset citations" and "fast retrieval" the same
architectural decision rather than a tradeoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi
from sqlalchemy import String, bindparam, text

import config
from db.connection import get_session
from rag.embedder import embed_query


@dataclass
class RetrievedChunk:
    """A single retrieved chunk with full source metadata.

    Attributes:
        content: Chunk text content.
        source_doc: Originating document filename.
        section: Section heading breadcrumb.
        page_number: Page number in the source document.
        dataset: Dataset metadata tag.
        scenario: Scenario metadata tag.
        region: Region metadata tag.
        ocr_extracted: True if this chunk came from an OCR fallback.
        score: Final reranker relevance score.
    """

    content: str
    source_doc: str
    section: str | None
    page_number: int
    dataset: str | None
    scenario: str | None
    region: str | None
    ocr_extracted: bool
    score: float = 0.0


_reranker = None


def _get_reranker():
    """Lazily loads and caches the cross-encoder reranker model."""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(config.RERANKER_MODEL)
    return _reranker


async def _sql_prefilter_and_vector_search(
    query_embedding: list[float], sql_filter: dict[str, Any]
) -> list[dict[str, Any]]:
    """Runs Stage 1 (SQL pre-filter on dataset/scenario/region) fused with
    Stage 2 (pgvector cosine similarity search) in a single query.

    Args:
        query_embedding: Embedded query vector.
        sql_filter: Dict with keys "dataset", "scenario", "region"
            (region may be a list including the parent region).

    Returns:
        List of candidate row dicts with similarity scores, ordered by
        similarity descending, limited to config.TOP_K_RETRIEVAL.
    """
    dataset = sql_filter.get("dataset")
    scenario = sql_filter.get("scenario")
    regions = sql_filter.get("region")
    if isinstance(regions, str):
        regions = [regions]

    # Every clause tolerates an untagged (NULL) column, including dataset.
    # A chunk whose metadata was never populated is a chunk we know nothing
    # about, not a chunk we know to be irrelevant — excluding it entirely
    # silently empties the corpus for any dataset the ingest run did not
    # tag, which turns retrieval into a no-op rather than a filter.
    conditions = [
        "(:dataset IS NULL OR dataset = :dataset OR dataset IS NULL)",
        "(:scenario IS NULL OR scenario = :scenario OR scenario IS NULL)",
    ]
    bind_params = [bindparam("dataset", type_=String), bindparam("scenario", type_=String)]
    params: dict[str, Any] = {
        "query_embedding": str(query_embedding),
        "dataset": dataset,
        "scenario": scenario,
        "limit": config.TOP_K_RETRIEVAL,
    }

    if regions:
        conditions.append("(region IN :regions OR region IS NULL)")
        bind_params.append(bindparam("regions", expanding=True))
        params["regions"] = regions

    query = text(
        f"""
        SELECT content, source_doc, section, page_number,
               dataset, scenario, region, ocr_extracted,
               1 - (embedding <=> :query_embedding) AS similarity
        FROM climate_chunks
        WHERE {" AND ".join(conditions)}
        ORDER BY embedding <=> :query_embedding
        LIMIT :limit
        """
    ).bindparams(*bind_params)

    async with get_session() as session:
        # ivfflat only probes a fraction of its clusters by default, which
        # can silently drop matching rows under a filtered ORDER BY/LIMIT
        # query. Raise it for this transaction so the pre-filter is exact.
        await session.execute(text(f"SET LOCAL ivfflat.probes = {int(config.IVFFLAT_PROBES)}"))
        result = await session.execute(
            query,
            {
                **params,
            },
        )
        rows = result.mappings().all()
    return [dict(row) for row in rows]


def _bm25_rerank(candidates: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Runs Stage 3 (BM25 keyword search) over the SQL-filtered candidates
    and fuses with the vector similarity ranking via reciprocal rank
    fusion (RRF).

    Args:
        candidates: Candidate rows from the SQL + vector search stage.
        query: Original natural-language query.

    Returns:
        Candidates re-ordered by fused RRF score (highest first).
    """
    if not candidates:
        return []

    tokenized_corpus = [c["content"].lower().split() for c in candidates]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(query.lower().split())

    vector_ranks = {i: rank for rank, i in enumerate(
        sorted(range(len(candidates)), key=lambda i: candidates[i]["similarity"], reverse=True)
    )}
    bm25_ranks = {i: rank for rank, i in enumerate(
        sorted(range(len(candidates)), key=lambda i: bm25_scores[i], reverse=True)
    )}

    k = 60  # standard RRF constant
    fused_scores = []
    for i in range(len(candidates)):
        rrf_score = 1.0 / (k + vector_ranks[i] + 1) + 1.0 / (k + bm25_ranks[i] + 1)
        fused_scores.append((rrf_score, i))

    fused_scores.sort(key=lambda x: x[0], reverse=True)
    return [candidates[i] for _, i in fused_scores]


def _cross_encoder_rerank(
    candidates: list[dict[str, Any]], query: str, top_k: int
) -> list[RetrievedChunk]:
    """Runs Stage 4 (cross-encoder reranking) over the fused candidates
    and returns the final top_k chunks with full source metadata.

    Args:
        candidates: RRF-fused candidate rows.
        query: Original natural-language query.
        top_k: Number of final chunks to return.

    Returns:
        List of RetrievedChunk, best first, length <= top_k.
    """
    if not candidates:
        return []

    reranker = _get_reranker()
    pairs = [(query, c["content"]) for c in candidates]
    scores = reranker.predict(pairs)

    scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        RetrievedChunk(
            content=c["content"],
            source_doc=c["source_doc"],
            section=c.get("section"),
            page_number=c["page_number"],
            dataset=c.get("dataset"),
            scenario=c.get("scenario"),
            region=c.get("region"),
            ocr_extracted=c.get("ocr_extracted", False),
            score=float(score),
        )
        for c, score in scored
    ]


async def retrieve(query: str, sql_filter: dict[str, Any]) -> list[RetrievedChunk]:
    """Runs the full four-stage hybrid retrieval pipeline.

    Args:
        query: The natural-language user query.
        sql_filter: Dict with "dataset", "scenario", "region" keys,
            produced by the KG agent's traversal result.

    Returns:
        Top config.TOP_K_RERANKED reranked chunks with source metadata.
        Returns an empty list (never hallucinated content) if no
        candidates survive the SQL pre-filter.
    """
    query_embedding = embed_query(query)
    candidates = await _sql_prefilter_and_vector_search(query_embedding, sql_filter)

    if not candidates:
        return []

    fused = _bm25_rerank(candidates, query)
    return _cross_encoder_rerank(fused, query, config.TOP_K_RERANKED)
