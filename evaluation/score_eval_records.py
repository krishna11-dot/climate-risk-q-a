"""Phase 2 of offline evaluation: scores the records written by
generate_eval_records.py using the REAL ragas library — genuine
LLM-judged faithfulness, answer_relevancy, and context_precision, not
the internal groundedness proxy.

This MUST run in the isolated `.venv-ragas` environment, never the main
project venv. Reason: ragas's dependency chain (an older
langchain-community) directly conflicts with the versions langgraph and
litellm need in production. Trying to satisfy both in one environment
previously broke the production pipeline outright. See
docs/maintenance-round-1-opus5.md and README.md for the incident.

The judge LLM reuses the project's existing Groq setup via LiteLLM —
no separate API key or provider. The one non-obvious piece: `instructor`
(ragas's structured-output library) defaults to OpenAI-style tool-calling
for extracting structured output, and Groq's tool-calling implementation
rejects it with a confusing "model does not exist" / "tool call
validation failed" error. Passing `mode=instructor.Mode.JSON` switches to
plain JSON-mode extraction, which Groq supports cleanly, and resolves it.

Usage (from climate_risk_agent/, after running generate_eval_records.py
in the MAIN venv):
    ./.venv-ragas/Scripts/python.exe evaluation/score_eval_records.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

import instructor
from datasets import Dataset
from litellm import acompletion
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed
from ragas import evaluate
from ragas.embeddings.base import BaseRagasEmbeddings
from ragas.llms import llm_factory
from ragas.metrics import answer_relevancy, context_precision, faithfulness
from ragas.run_config import RunConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_RECORDS_PATH = Path(__file__).resolve().parent / "eval_records.json"

# Model names are read from the same environment variables config.py uses,
# so this stays consistent with the rest of the project without importing
# config.py itself (config.py pulls in the full app dependency chain,
# which is exactly what this isolated venv exists to avoid).
_JUDGE_MODEL = os.getenv("SUPERVISOR_MODEL", "groq/openai/gpt-oss-20b")
_RAGAS_THRESHOLD = float(os.getenv("RAGAS_THRESHOLD", "0.80"))
_FAITHFULNESS_SEGMENT_THRESHOLD = float(
    os.getenv("FAITHFULNESS_SEGMENT_THRESHOLD", "0.80")
)


def _build_judge() -> Any:
    """Builds the RAGAS judge LLM using the project's existing Groq setup.

    Returns:
        A ragas-compatible LLM object backed by LiteLLM + Groq.
    """
    client = instructor.from_litellm(acompletion, mode=instructor.Mode.JSON)
    # instructor's own default retry (3 attempts, short exponential backoff)
    # gives up faster than Groq's free-tier TPM bucket (8000/min) can refill,
    # so every retry after a rate-limit hit fails for the same reason as the
    # first call. A fixed 15s wait is long enough to free up headroom between
    # attempts; this is on top of RunConfig(max_workers=1) below, which stops
    # ragas from firing multiple judge calls concurrently in the first place.
    retrying = AsyncRetrying(stop=stop_after_attempt(6), wait=wait_fixed(15))
    # ragas's default max_tokens (1024) is too small for faithfulness's
    # claim-extraction + verification JSON against real multi-chunk contexts —
    # it was truncating mid-JSON ("max completion tokens reached before
    # generating a valid document"), which ragas silently scored as nan
    # instead of surfacing as a real generation failure.
    return llm_factory(
        model=_JUDGE_MODEL,
        provider="groq",
        client=client,
        max_retries=retrying,
        max_tokens=4096,
    )


class _SentenceTransformerEmbeddings(BaseRagasEmbeddings):
    """Minimal RAGAS embeddings adapter backed by sentence-transformers
    directly.

    Deliberately avoids `langchain-huggingface`: installing it pulled in
    a newer `langchain-core` that broke the older `langchain-community`/
    `langchain-openai` pins this isolated venv needs to keep ragas's own
    imports working (see the module docstring). Talking to
    sentence-transformers directly sidesteps that whole conflict.
    """

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        super().__init__()
        self._model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, show_progress_bar=False).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, text)


def _build_embeddings() -> _SentenceTransformerEmbeddings:
    """Builds the embedding model answer_relevancy needs, reusing the
    same local model the production RAG pipeline uses (no API cost).

    Returns:
        A ragas-compatible embeddings wrapper.
    """
    model_name = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    return _SentenceTransformerEmbeddings(model_name)


def _segment_by_region(
    records: list[dict[str, Any]], per_row_faithfulness: list[float]
) -> dict[str, float]:
    """Computes average REAL faithfulness per region segment.

    Args:
        records: The eval records (same order as per_row_faithfulness).
        per_row_faithfulness: Real ragas faithfulness score per record.

    Returns:
        Dict of region -> average faithfulness score.
    """
    by_region: dict[str, list[float]] = defaultdict(list)
    for record, score in zip(records, per_row_faithfulness):
        region = record.get("region") or "unspecified"
        by_region[region].append(score)
    return {region: sum(scores) / len(scores) for region, scores in by_region.items()}


def score() -> bool:
    """Scores evaluation/eval_records.json with real RAGAS metrics.

    Returns:
        True if all overall and per-segment thresholds pass.
    """
    if not _RECORDS_PATH.exists():
        raise FileNotFoundError(
            f"{_RECORDS_PATH} not found. Run generate_eval_records.py in "
            "the MAIN venv first: ./.venv/Scripts/python.exe "
            "evaluation/generate_eval_records.py"
        )

    with _RECORDS_PATH.open("r", encoding="utf-8") as f:
        records = json.load(f)

    scoreable = [r for r in records if r["contexts"]]
    skipped = len(records) - len(scoreable)
    if skipped:
        logger.warning(
            "Skipping %d record(s) with no retrieved context (e.g. blocked "
            "or out-of-scope queries) — RAGAS scores grounded answers, not "
            "intentional refusals.",
            skipped,
        )
    if not scoreable:
        logger.error("No records with retrieved context to score.")
        return False

    dataset = Dataset.from_list(
        [
            {
                "question": r["question"],
                "answer": r["answer"],
                "contexts": r["contexts"],
                "reference": r.get("reference", ""),
            }
            for r in scoreable
        ]
    )

    judge = _build_judge()
    embeddings = _build_embeddings()

    # Groq's free tier caps this judge model at 8000 tokens/minute. Ragas's
    # default RunConfig fires up to 16 judge calls concurrently, which blows
    # past that limit almost immediately (the sequential generate_eval_records.py
    # never hits this because it makes one pipeline call at a time). Serializing
    # to one worker keeps us under the TPM ceiling; tenacity's built-in retry
    # (max_wait=60s) absorbs the rest.
    run_config = RunConfig(max_workers=1, max_wait=60, max_retries=10)

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=judge,
        embeddings=embeddings,
        run_config=run_config,
    )

    per_row = result.to_pandas()
    metric_names = ["faithfulness", "answer_relevancy", "context_precision"]
    overall_metrics = {m: float(per_row[m].mean()) for m in metric_names}
    segment_scores = _segment_by_region(scoreable, per_row["faithfulness"].tolist())

    logger.info("Overall RAGAS metrics (real, LLM-judged): %s", overall_metrics)
    logger.info("Per-region faithfulness: %s", segment_scores)

    passed = True
    for metric_name, value in overall_metrics.items():
        if value < _RAGAS_THRESHOLD:
            logger.error(
                "Metric %s=%.3f below threshold %.2f", metric_name, value, _RAGAS_THRESHOLD
            )
            passed = False

    for region, value in segment_scores.items():
        if value < _FAITHFULNESS_SEGMENT_THRESHOLD:
            logger.error(
                "Region %s faithfulness=%.3f below segment threshold %.2f",
                region, value, _FAITHFULNESS_SEGMENT_THRESHOLD,
            )
            passed = False

    return passed


if __name__ == "__main__":
    ok = score()
    sys.exit(0 if ok else 1)
