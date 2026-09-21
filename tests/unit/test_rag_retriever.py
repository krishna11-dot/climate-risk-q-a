"""Unit tests for rag/retriever.py's fusion/reranking stages and
rag/chunker.py's chunking behavior, without requiring a live database.
"""

from __future__ import annotations

from rag.chunker import chunk_document, detect_tables, strip_boilerplate
from rag.retriever import _bm25_rerank


def test_strip_boilerplate_removes_repeated_lines() -> None:
    pages = [
        "Header X\nContent page one.\nFooter Y",
        "Header X\nContent page two.\nFooter Y",
        "Header X\nContent page three.\nFooter Y",
    ]
    cleaned = strip_boilerplate(pages)
    assert all("Header X" not in page for page in cleaned)
    assert all("Footer Y" not in page for page in cleaned)
    assert "Content page one." in cleaned[0]


def test_detect_tables_finds_pipe_table() -> None:
    text = "Some intro text.\n| A | B |\n| 1 | 2 |\nMore text after."
    tables = detect_tables(text)
    assert len(tables) == 1
    assert "| A | B |" in tables[0][2]


def test_chunk_document_preserves_table_as_atomic_unit() -> None:
    pages = ["Intro.\n| A | B |\n| 1 | 2 |\n| 3 | 4 |\nOutro text here."]
    chunks = chunk_document(pages)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert "| 1 | 2 |" in table_chunks[0].content
    assert "| 3 | 4 |" in table_chunks[0].content


def test_chunk_document_carries_section_breadcrumb() -> None:
    chunks = chunk_document(["Some content here."], section_headings=["Flood Risk"])
    assert all("[Section: Flood Risk]" in c.content for c in chunks)


def test_bm25_rerank_returns_all_candidates() -> None:
    candidates = [
        {"content": "flood risk precipitation Kerala CMIP6", "similarity": 0.9},
        {"content": "unrelated text about heat London", "similarity": 0.5},
    ]
    reranked = _bm25_rerank(candidates, "flood risk Kerala")
    assert len(reranked) == 2
    assert reranked[0]["content"].startswith("flood")


def test_bm25_rerank_empty_input() -> None:
    assert _bm25_rerank([], "any query") == []
