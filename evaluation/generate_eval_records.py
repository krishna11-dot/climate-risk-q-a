"""Phase 1 of offline evaluation: runs the real pipeline for every item in
test_dataset.json and writes the raw records (question/answer/contexts/
region) to disk as JSON.

This MUST run in the main project venv, since it needs langgraph, litellm,
and the full agent stack. It deliberately does not import ragas at all —
see docs/ragas-isolated-venv.md for why RAGAS lives in a separate venv
(.venv-ragas) with an older langchain-community that conflicts with the
production langgraph/litellm dependency chain.

Usage:
    ./.venv/Scripts/python.exe evaluation/generate_eval_records.py

Output:
    evaluation/eval_records.json — consumed by score_eval_records.py,
    which runs in the isolated .venv-ragas.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.workflow import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_OUTPUT_PATH = Path(__file__).resolve().parent / "eval_records.json"


async def _run_query_for_eval(item: dict[str, Any]) -> dict[str, Any]:
    """Runs the pipeline for one test dataset item and extracts the raw
    fields needed for RAGAS scoring plus the region for segmentation.

    Args:
        item: One entry from test_dataset.json.

    Returns:
        Dict with question, answer, contexts, reference, region, and the
        internal groundedness proxy (kept only as a fallback label, not
        used once real RAGAS scores are available).
    """
    state = await run_pipeline(item["question"])
    contexts = [c["content"] for c in (state.rag_results or [])]
    return {
        "id": item["id"],
        "region": item.get("region"),
        "question": item["question"],
        "answer": state.final_answer or "",
        "contexts": contexts,
        # context_precision requires a ground-truth reference answer.
        # test_dataset.json doesn't define one per item yet, so this
        # falls back to the item's own expected_behavior label — good
        # enough to exercise the metric, not a substitute for real
        # human-authored reference answers.
        "reference": item.get("reference", item.get("expected_behavior", "")),
        "groundedness_proxy": state.groundedness_score or 0.0,
    }


async def generate(dataset_path: str = "evaluation/test_dataset.json") -> None:
    """Runs the pipeline for every test item and writes records to disk.

    Args:
        dataset_path: Path to the JSON test dataset.
    """
    # Blocking file I/O in an async function normally risks stalling other
    # tasks sharing the event loop, but this script is a one-shot batch
    # job with nothing else running concurrently on it, so that concern
    # doesn't apply here.
    with Path(dataset_path).open("r", encoding="utf-8") as f:  # noqa: ASYNC230
        items = json.load(f)

    # Sequential, not gathered: Groq's free tier enforces a shared
    # per-minute output-token budget across all calls to a given model,
    # so firing all items concurrently reliably triggers rate limits.
    records = [await _run_query_for_eval(item) for item in items]

    with _OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    logger.info("Wrote %d eval records to %s", len(records), _OUTPUT_PATH)


if __name__ == "__main__":
    asyncio.run(generate())
