"""Local CPU embedding via sentence-transformers (all-MiniLM-L6-v2, 384d).

Running embeddings locally avoids any per-call API cost and keeps the
free-tier stack fully free for embedding-heavy ingestion workloads.
"""

from __future__ import annotations

import config

_model = None


def _get_model():
    """Lazily loads and caches the sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embeds a batch of texts into 384-dimensional vectors.

    Args:
        texts: List of chunk content strings to embed.

    Returns:
        List of embedding vectors, one per input text, each of length
        config.PGVECTOR_DIMS.
    """
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, batch_size=32, show_progress_bar=False)
    return [vector.tolist() for vector in vectors]


def embed_query(query: str) -> list[float]:
    """Embeds a single query string for similarity search.

    Args:
        query: The natural-language query text.

    Returns:
        A single embedding vector of length config.PGVECTOR_DIMS.
    """
    return embed_texts([query])[0]
