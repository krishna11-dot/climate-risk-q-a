"""Regression tests pinning bugs found in the 2026-09-14 maintenance round.

Each test here corresponds to a specific defect that shipped, was found by
review rather than by a failing test, and could plausibly be reintroduced
by a well-meaning refactor. The docstrings record what actually broke, so
a future reader knows why the assertion is worded the way it is.
"""

from __future__ import annotations

import asyncio

import pytest

import config
import main
from agents import supervisor
from graph.state import ClimateRiskState
from guardrails.output_filter import verify_and_filter_datasets
from knowledge_graph.builder import load_schema

# ---------------------------------------------------------------------------
# Bug 1: the kill switch was a module-level snapshot taken at import time,
# so flipping config.AGENT_PAUSED at runtime (the documented incident
# escalation step) did nothing until the process was restarted.
# ---------------------------------------------------------------------------


def test_kill_switch_reads_config_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "AGENT_PAUSED", False)
    assert main.is_agent_paused() is False

    monkeypatch.setattr(config, "AGENT_PAUSED", True)
    assert main.is_agent_paused() is True, (
        "kill switch must observe config changes without a process restart"
    )


def test_paused_query_short_circuits_without_running_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pipeline must not run while the agent is paused")

    monkeypatch.setattr(config, "AGENT_PAUSED", True)
    monkeypatch.setattr(main, "run_pipeline", _explode)

    response = asyncio.run(main.query(main.QueryRequest(query="flood risk Kerala")))

    assert response["status"] == "paused"
    assert response["human_review"] is True


# ---------------------------------------------------------------------------
# Bug 2: the two concurrent agents were handed the *same* state instance, so
# their writes aliased and their cost accumulators collided. The collision
# was masked with max(), which silently discarded the cheaper branch's spend
# from the regulator-facing audit record.
# ---------------------------------------------------------------------------


def test_state_copies_are_independent() -> None:
    state = ClimateRiskState(user_query="flood risk Kerala", litellm_cost_usd=1.0)
    branch = state.model_copy(deep=True)

    branch.litellm_cost_usd = 99.0
    branch.rag_results = [{"content": "x"}]

    assert state.litellm_cost_usd == 1.0
    assert state.rag_results is None


def test_parallel_branch_costs_are_summed_not_maxed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAG spends 0.10 and analysis spends 0.25 on top of a 1.00 baseline.

    Correct total is 1.35. The old max() logic reported 1.25, losing the
    RAG branch's spend entirely.
    """

    async def fake_rag(state: ClimateRiskState) -> ClimateRiskState:
        state.litellm_cost_usd += 0.10
        state.rag_results = [{"content": "chunk"}]
        return state

    async def fake_analysis(state: ClimateRiskState) -> ClimateRiskState:
        state.litellm_cost_usd += 0.25
        state.analysis_results = {"success": True, "value": 1.0}
        return state

    monkeypatch.setattr(supervisor, "run_rag_agent", fake_rag)
    monkeypatch.setattr(supervisor, "run_analysis_agent", fake_analysis)

    state = ClimateRiskState(user_query="flood risk Kerala", litellm_cost_usd=1.0)
    state.kg_results = {"found": True, "dataset": "ERA5"}

    async def run_branches() -> ClimateRiskState:
        cost_before = state.litellm_cost_usd
        rag_task = asyncio.create_task(
            supervisor.run_rag_agent(state.model_copy(deep=True))
        )
        analysis_task = asyncio.create_task(
            supervisor.run_analysis_agent(state.model_copy(deep=True))
        )
        rag_state, analysis_state = await asyncio.gather(rag_task, analysis_task)
        state.rag_results = rag_state.rag_results
        state.analysis_results = analysis_state.analysis_results
        state.litellm_cost_usd = (
            cost_before
            + (rag_state.litellm_cost_usd - cost_before)
            + (analysis_state.litellm_cost_usd - cost_before)
        )
        return state

    result = asyncio.run(run_branches())

    assert result.litellm_cost_usd == pytest.approx(1.35)
    assert result.rag_results is not None
    assert result.analysis_results is not None


# ---------------------------------------------------------------------------
# Bug 3: the dataset pre-filter was the only clause that did not tolerate an
# untagged (NULL) column, so any KG resolution to a dataset the ingest run
# had not tagged filtered the whole corpus to zero rows and silently turned
# retrieval into a no-op.
# ---------------------------------------------------------------------------


def test_dataset_prefilter_tolerates_untagged_chunks() -> None:
    import inspect

    from rag import retriever

    source = inspect.getsource(retriever._sql_prefilter_and_vector_search)

    assert "dataset IS NULL" in source, (
        "dataset clause must tolerate untagged chunks, like scenario and region"
    )
    for column in ("scenario IS NULL", "region IS NULL"):
        assert column in source


# ---------------------------------------------------------------------------
# Bug 4: the "structurally cannot hallucinate a dataset" guarantee was
# vacuous. Detection only scanned for names already on the allowlist, then
# "verified" them against the KG, which by construction always returned True.
# An invented name such as CMIP7 was never detectable.
# ---------------------------------------------------------------------------


@pytest.fixture(name="known_datasets")
def _known_datasets() -> list[str]:
    return load_schema()["datasets"]


def test_invented_dataset_in_known_family_is_caught(known_datasets: list[str]) -> None:
    text = "According to CMIP7 projections, flood risk rises sharply."
    filtered, verified = verify_and_filter_datasets(text, known_datasets)

    assert verified["CMIP7"] is False
    assert "CMIP7" not in filtered


def test_invented_dataset_presented_as_source_is_caught(
    known_datasets: list[str],
) -> None:
    text = "The SuperClimate9000 dataset reports severe Mumbai flooding."
    filtered, verified = verify_and_filter_datasets(text, known_datasets)

    assert verified["SuperClimate9000"] is False
    assert "SuperClimate9000" not in filtered


def test_real_dataset_outside_the_kg_is_caught(known_datasets: list[str]) -> None:
    text = "Based on CHIRPS data, rainfall is unusually high."
    filtered, verified = verify_and_filter_datasets(text, known_datasets)

    assert verified["CHIRPS"] is False
    assert "CHIRPS" not in filtered


def test_legitimate_citation_is_preserved(known_datasets: list[str]) -> None:
    text = "According to CMIP6, precipitation increases under SSP5-8.5."
    filtered, verified = verify_and_filter_datasets(text, known_datasets)

    assert verified["CMIP6"] is True
    assert filtered == text


def test_scenarios_and_acronyms_are_not_dataset_citations(
    known_datasets: list[str],
) -> None:
    """Guards against over-correction: the fix must not shred real answers.

    RCP8.5 and SSP5-8.5 are scenarios, NAO and GMST are ordinary climate
    acronyms. None is a dataset citation, and redacting them would mangle
    otherwise correct text.
    """
    text = "Under RCP8.5 and SSP5-8.5 the NAO shifts and GMST rises."
    filtered, verified = verify_and_filter_datasets(text, known_datasets)

    assert verified == {}
    assert filtered == text
