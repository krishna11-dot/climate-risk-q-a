"""Guardrail layer 2: knowledge graph gate.

Runs immediately after the KG agent. If the KG traversal (including all
fallback tiers) could not resolve a dataset, this gate hard-stops the
pipeline with an honest coverage-gap message rather than allowing the
RAG or analysis agents to proceed on ungrounded assumptions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from knowledge_graph.query import KGLookupResult

logger = logging.getLogger(__name__)

_COVERAGE_GAP_LOG_PATH = Path("audit/kg_coverage_gaps.jsonl")


@dataclass
class KGGateResult:
    """Result of the KG gate check.

    Attributes:
        passed: True if the KG gate allows the pipeline to continue.
        user_message: Honest, user-facing message when the gate blocks.
    """

    passed: bool
    user_message: str | None = None


def _log_coverage_gap(kg_result: KGLookupResult) -> None:
    """Appends a coverage gap record for future KG expansion planning.

    Args:
        kg_result: The failed KGLookupResult to log.
    """
    _COVERAGE_GAP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "hazard": kg_result.hazard,
        "region": kg_result.region,
        "scenario": kg_result.scenario,
        "nodes_traversed": kg_result.nodes_traversed,
    }
    with _COVERAGE_GAP_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    logger.warning("KG coverage gap logged: %s", record)


def check_kg_gate(kg_result: KGLookupResult) -> KGGateResult:
    """Checks the KG gate: hard-stops on coverage_gap=True.

    Args:
        kg_result: The KGLookupResult returned by the KG agent.

    Returns:
        A KGGateResult indicating whether the pipeline may proceed.
    """
    if kg_result.coverage_gap:
        _log_coverage_gap(kg_result)
        return KGGateResult(
            passed=False,
            user_message=(
                f"No verified climate dataset covers '{kg_result.hazard}' risk "
                f"for '{kg_result.region}' under scenario '{kg_result.scenario}', "
                "even after checking parent regions and adjacent scenarios. "
                "This is an honest coverage gap in the current knowledge graph, "
                "not a system error. It has been logged for future data expansion."
            ),
        )
    return KGGateResult(passed=True)
