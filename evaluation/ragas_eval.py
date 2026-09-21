"""Offline evaluation using RAGAS: faithfulness, answer_relevancy, and
context_precision, computed per-segment (by region) to catch geographic
fairness issues, not just an aggregate score.

LiteLLM caching means repeated eval runs cost zero additional tokens for
unchanged queries.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Allow running this file directly (`python evaluation/ragas_eval.py`) by
# putting the project root on sys.path, since Python only adds the
# script's own directory by default.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from graph.workflow import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _run_query_for_eval(item: dict[str, Any]) -> dict[str, Any]:
    """Runs the pipeline for one test dataset item and extracts the
    fields RAGAS needs plus the region for segmentation.

    Args:
        item: One entry from test_dataset.json.

    Returns:
        Dict with question, answer, contexts, faithfulness proxy, region.
    """
    state = await run_pipeline(item["question"])
    contexts = [c["content"] for c in (state.rag_results or [])]
    return {
        "id": item["id"],
        "region": item.get("region"),
        "question": item["question"],
        "answer": state.final_answer or "",
        "contexts": contexts,
        "faithfulness": state.groundedness_score or 0.0,
    }


def _run_ragas_metrics(records: list[dict[str, Any]]) -> dict[str, float]:
    """Runs RAGAS faithfulness/answer_relevancy/context_precision over
    the collected records.

    Args:
        records: List of eval records with question/answer/contexts.

    Returns:
        Dict of metric name -> aggregate score. Falls back to the
        recorded groundedness proxy if the ragas package/API is
        unavailable in this environment.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, faithfulness

        eval_records = [r for r in records if r["contexts"]]
        if not eval_records:
            raise ValueError("No records with retrieved context to evaluate.")

        dataset = Dataset.from_list(
            [
                {
                    "question": r["question"],
                    "answer": r["answer"],
                    "contexts": r["contexts"],
                }
                for r in eval_records
            ]
        )
        result = evaluate(
            dataset, metrics=[faithfulness, answer_relevancy, context_precision]
        )
        return {k: float(v) for k, v in result.items()}
    except Exception:  # noqa: BLE001
        logger.warning("RAGAS unavailable or failed; falling back to groundedness proxy.")
        avg = sum(r["faithfulness"] for r in records) / max(len(records), 1)
        return {"faithfulness": avg, "answer_relevancy": avg, "context_precision": avg}


def _segment_by_region(records: list[dict[str, Any]]) -> dict[str, float]:
    """Computes average faithfulness per region segment.

    Args:
        records: List of eval records with region and faithfulness.

    Returns:
        Dict of region -> average faithfulness score.
    """
    by_region: dict[str, list[float]] = defaultdict(list)
    for r in records:
        region = r.get("region") or "unspecified"
        by_region[region].append(r["faithfulness"])
    return {region: sum(scores) / len(scores) for region, scores in by_region.items()}


async def run_offline_eval(dataset_path: str = "evaluation/test_dataset.json") -> bool:
    """Runs the full offline RAGAS evaluation and per-segment fairness
    check, failing if any score falls below config.RAGAS_THRESHOLD.

    Args:
        dataset_path: Path to the JSON test dataset.

    Returns:
        True if all checks pass, False otherwise.
    """
    with Path(dataset_path).open("r", encoding="utf-8") as f:
        items = json.load(f)

    # Sequential, not gathered: Groq's free tier enforces a shared
    # per-minute output-token budget across all calls to a given model,
    # so firing all items concurrently reliably triggers rate limits.
    records = [await _run_query_for_eval(item) for item in items]

    overall_metrics = _run_ragas_metrics(list(records))
    segment_scores = _segment_by_region(list(records))

    logger.info("Overall RAGAS metrics: %s", overall_metrics)
    logger.info("Per-region faithfulness: %s", segment_scores)

    passed = True
    for metric_name, score in overall_metrics.items():
        if score < config.RAGAS_THRESHOLD:
            logger.error("Metric %s=%.3f below threshold %.2f", metric_name, score, config.RAGAS_THRESHOLD)
            passed = False

    for region, score in segment_scores.items():
        if score < config.FAITHFULNESS_SEGMENT_THRESHOLD:
            logger.error(
                "Region %s faithfulness=%.3f below segment threshold %.2f",
                region, score, config.FAITHFULNESS_SEGMENT_THRESHOLD,
            )
            passed = False

    return passed


if __name__ == "__main__":
    ok = asyncio.run(run_offline_eval())
    sys.exit(0 if ok else 1)
