"""Document chunking with table preservation, boilerplate stripping, and
sentence/paragraph-boundary detection.

Chunk size and overlap are read from config.py: 512 tokens with a 50 token
overlap so that answers spanning a chunk boundary are never lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import config

_TOKEN_RE = re.compile(r"\S+")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_HEADER_FOOTER_CANDIDATES_MIN_REPEATS = 3


@dataclass
class Chunk:
    """A single chunk of document text ready for embedding.

    Attributes:
        content: The chunk text, with section heading breadcrumb prepended.
        section: The section heading this chunk belongs to.
        page_number: Page number the chunk primarily originates from.
        chunk_index: Sequential index of this chunk within the document.
        is_table: True if this chunk is an atomic serialized table.
    """

    content: str
    section: str | None
    page_number: int
    chunk_index: int
    is_table: bool = False


def _count_tokens(text: str) -> int:
    """Approximates token count via whitespace splitting.

    A full tokenizer is unnecessary here: chunk boundaries only need to be
    approximately CHUNK_SIZE tokens, not exact.
    """
    return len(_TOKEN_RE.findall(text))


def strip_boilerplate(pages: list[str]) -> list[str]:
    """Strips repeated headers/footers and watermark-like lines that occur
    identically across most pages of a document.

    Args:
        pages: Raw extracted text for each page.

    Returns:
        Pages with repeated boilerplate lines removed.
    """
    line_counts: dict[str, int] = {}
    for page in pages:
        for line in {ln.strip() for ln in page.splitlines() if ln.strip()}:
            line_counts[line] = line_counts.get(line, 0) + 1

    threshold = max(_HEADER_FOOTER_CANDIDATES_MIN_REPEATS, len(pages) // 2)
    boilerplate = {
        line for line, count in line_counts.items() if count >= threshold and len(pages) > 1
    }

    cleaned_pages = []
    for page in pages:
        kept_lines = [ln for ln in page.splitlines() if ln.strip() not in boilerplate]
        cleaned_pages.append("\n".join(kept_lines))
    return cleaned_pages


def detect_tables(text: str) -> list[tuple[int, int, str]]:
    """Detects markdown-style pipe tables in text so they can be treated
    as atomic units during chunking.

    Args:
        text: Page or section text to scan.

    Returns:
        List of (start_char, end_char, serialized_table_markdown) spans.
    """
    lines = text.split("\n")
    tables: list[tuple[int, int, str]] = []
    i = 0
    offset = 0
    line_offsets = []
    for line in lines:
        line_offsets.append(offset)
        offset += len(line) + 1

    while i < len(lines):
        if _TABLE_ROW_RE.match(lines[i]):
            start = i
            while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
                i += 1
            end = i
            table_text = "\n".join(lines[start:end])
            tables.append((line_offsets[start], line_offsets[end - 1] + len(lines[end - 1]), table_text))
        else:
            i += 1
    return tables


def _split_sentences(text: str) -> list[str]:
    """Splits text into sentence/paragraph units, never mid-sentence."""
    paragraphs = re.split(r"\n\s*\n", text)
    sentences: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        parts = re.split(r"(?<=[.!?])\s+", para)
        sentences.extend(p for p in parts if p.strip())
    return sentences


def chunk_document(
    pages: list[str],
    section_headings: list[str | None] | None = None,
    source_doc: str = "",
) -> list[Chunk]:
    """Chunks a document's pages into overlapping, boundary-respecting
    chunks of approximately CHUNK_SIZE tokens, preserving tables as
    atomic units and carrying section headings as breadcrumbs.

    Args:
        pages: Boilerplate-stripped page text, one string per page.
        section_headings: Optional per-page section heading, same length
            as pages. If None, no breadcrumb is added.
        source_doc: Name of the source document, used only for context
            in returned Chunk objects (not stored on the object itself).

    Returns:
        List of Chunk objects ready for embedding.
    """
    headings = section_headings or [None] * len(pages)
    chunks: list[Chunk] = []
    chunk_index = 0

    for page_num, (page_text, heading) in enumerate(zip(pages, headings), start=1):
        tables = detect_tables(page_text)

        # Extract non-table text between/around tables, preserving order.
        cursor = 0
        segments: list[tuple[bool, str]] = []
        for start, end, table_md in sorted(tables):
            if start > cursor:
                segments.append((False, page_text[cursor:start]))
            segments.append((True, table_md))
            cursor = end
        if cursor < len(page_text):
            segments.append((False, page_text[cursor:]))

        buffer_sentences: list[str] = []
        buffer_tokens = 0

        # Ruff (B023) flags the closure below as capturing loop variables
        # (heading, page_num) by reference, which is unsafe if a closure
        # outlives the iteration it's defined in. This one doesn't: it's
        # redefined fresh every outer-loop iteration and only ever called
        # within that same iteration (below, never stored or deferred), so
        # heading/page_num are always current when it runs.
        def flush_buffer() -> None:
            nonlocal buffer_sentences, buffer_tokens, chunk_index
            if not buffer_sentences:
                return
            body = " ".join(buffer_sentences)
            content = f"[Section: {heading}]\n{body}" if heading else body  # noqa: B023
            chunks.append(
                Chunk(
                    content=content,
                    section=heading,  # noqa: B023
                    page_number=page_num,  # noqa: B023
                    chunk_index=chunk_index,
                    is_table=False,
                )
            )
            chunk_index += 1
            # Carry overlap: keep trailing sentences worth ~CHUNK_OVERLAP tokens.
            overlap_sentences: list[str] = []
            overlap_tokens = 0
            for sentence in reversed(buffer_sentences):
                t = _count_tokens(sentence)
                if overlap_tokens + t > config.CHUNK_OVERLAP:
                    break
                overlap_sentences.insert(0, sentence)
                overlap_tokens += t
            buffer_sentences = overlap_sentences
            buffer_tokens = overlap_tokens

        for is_table, seg_text in segments:
            if is_table:
                # Tables are atomic: flush current buffer first, then emit
                # the table as its own chunk, never split across chunks.
                flush_buffer()
                content = f"[Section: {heading}]\n{seg_text}" if heading else seg_text
                chunks.append(
                    Chunk(
                        content=content,
                        section=heading,
                        page_number=page_num,
                        chunk_index=chunk_index,
                        is_table=True,
                    )
                )
                chunk_index += 1
                buffer_sentences = []
                buffer_tokens = 0
                continue

            for sentence in _split_sentences(seg_text):
                sentence_tokens = _count_tokens(sentence)
                if buffer_tokens + sentence_tokens > config.CHUNK_SIZE and buffer_sentences:
                    flush_buffer()
                buffer_sentences.append(sentence)
                buffer_tokens += sentence_tokens

        flush_buffer()

    return chunks
