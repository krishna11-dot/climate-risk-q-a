"""PDF ingestion pipeline: extract -> OCR fallback -> chunk -> embed -> store.

Idempotent by design: re-running against the same PDFs is safe because
inserts use ON CONFLICT (source_doc, page_number, chunk_index) DO NOTHING.

TODO: download UKCP18 PDFs from the UK Met Office website into
config.UKCP18_PDF_DIR before running this script.
"""

from __future__ import annotations

import asyncio
import io
import logging
import sys
from pathlib import Path

# Allow running this file directly (`python rag/ingest.py`) by putting
# the project root on sys.path, since Python only adds the script's own
# directory by default.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # PyMuPDF
from sqlalchemy import text

import config
from db.connection import get_session
from rag.chunker import chunk_document, strip_boilerplate
from rag.embedder import embed_texts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_OCR_MIN_CHARS = 50


def extract_pages(pdf_path: Path) -> tuple[list[str], list[bool]]:
    """Extracts text per page from a PDF, falling back to OCR for pages
    with little or no extractable text (e.g. scanned appendices).

    Args:
        pdf_path: Path to the source PDF file.

    Returns:
        Tuple of (page_texts, ocr_flags) where ocr_flags[i] is True if
        page i required OCR extraction.
    """
    doc = fitz.open(pdf_path)
    page_texts: list[str] = []
    ocr_flags: list[bool] = []

    for page in doc:
        raw_text = page.get_text().strip()
        if len(raw_text) >= _OCR_MIN_CHARS:
            page_texts.append(raw_text)
            ocr_flags.append(False)
            continue

        # Rasterize and OCR the page — handles scanned appendices.
        import pytesseract
        from PIL import Image

        pix = page.get_pixmap(dpi=300)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        ocr_text = pytesseract.image_to_string(image)
        page_texts.append(ocr_text.strip())
        ocr_flags.append(True)

    doc.close()
    return page_texts, ocr_flags


async def ingest_pdf(
    pdf_path: Path,
    dataset: str | None = None,
    scenario: str | None = None,
    region: str | None = None,
    version: str | None = None,
) -> tuple[int, int]:
    """Ingests a single PDF end to end: extract, OCR fallback, chunk,
    embed, and idempotently insert into climate_chunks.

    Args:
        pdf_path: Path to the PDF file.
        dataset: Dataset metadata tag to attach to every chunk.
        scenario: Scenario metadata tag to attach to every chunk.
        region: Region metadata tag to attach to every chunk.
        version: Document version tag to attach to every chunk.

    Returns:
        Tuple of (new_chunks_count, skipped_chunks_count).
    """
    page_texts, ocr_flags = extract_pages(pdf_path)
    cleaned_pages = strip_boilerplate(page_texts)
    chunks = chunk_document(cleaned_pages, source_doc=pdf_path.name)

    if not chunks:
        logger.info("No chunks produced for %s", pdf_path.name)
        return 0, 0

    embeddings = embed_texts([c.content for c in chunks])

    new_count = 0
    skipped_count = 0

    async with get_session() as session:
        for chunk, embedding in zip(chunks, embeddings):
            ocr_extracted = ocr_flags[chunk.page_number - 1] if chunk.page_number - 1 < len(ocr_flags) else False
            result = await session.execute(
                text(
                    """
                    INSERT INTO climate_chunks
                        (content, embedding, source_doc, section, page_number,
                         chunk_index, ocr_extracted, dataset, scenario, region, version)
                    VALUES
                        (:content, :embedding, :source_doc, :section, :page_number,
                         :chunk_index, :ocr_extracted, :dataset, :scenario, :region, :version)
                    ON CONFLICT (source_doc, page_number, chunk_index) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "content": chunk.content,
                    "embedding": str(embedding),
                    "source_doc": pdf_path.name,
                    "section": chunk.section,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "ocr_extracted": ocr_extracted,
                    "dataset": dataset,
                    "scenario": scenario,
                    "region": region,
                    "version": version,
                },
            )
            if result.first() is not None:
                new_count += 1
            else:
                skipped_count += 1
        await session.commit()

    logger.info(
        "Ingested %s: %d new chunks, %d skipped (already present)",
        pdf_path.name,
        new_count,
        skipped_count,
    )
    return new_count, skipped_count


async def ingest_directory(pdf_dir: str | None = None, dataset: str = "UKCP18") -> None:
    """Ingests every PDF in a directory.

    Args:
        pdf_dir: Directory containing PDFs. Defaults to
            config.UKCP18_PDF_DIR.
        dataset: Dataset tag applied to every ingested chunk, so the SQL
            pre-filter in rag/retriever.py can match on it. Defaults to
            "UKCP18" since config.UKCP18_PDF_DIR is a UKCP18-only source.
    """
    # TODO: configure UKCP18 PDF paths — populate config.UKCP18_PDF_DIR
    # with downloaded PDFs before calling this function.
    directory = Path(pdf_dir or config.UKCP18_PDF_DIR)
    if not directory.exists():
        logger.warning("PDF directory %s does not exist. Skipping ingest.", directory)
        return

    pdf_paths = sorted(directory.glob("*.pdf"))
    if not pdf_paths:
        logger.warning("No PDFs found in %s.", directory)
        return

    total_new, total_skipped = 0, 0
    for pdf_path in pdf_paths:
        new_count, skipped_count = await ingest_pdf(pdf_path, dataset=dataset)
        total_new += new_count
        total_skipped += skipped_count

    logger.info("Ingestion complete: %d new chunks, %d skipped total", total_new, total_skipped)


if __name__ == "__main__":
    asyncio.run(ingest_directory())
