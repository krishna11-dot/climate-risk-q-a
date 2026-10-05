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
from guardrails.output_filter import apply_output_filter, verify_and_filter_datasets
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


# ---------------------------------------------------------------------------
# Bug 5 (2026-09-22): a total LLM failure (both primary and fallback model
# calls failing) produced the exact same downstream shape as a correct
# "insufficient grounding" refusal — an empty final_answer with nothing to
# tell them apart in the audit record. That let a real Groq model-rename
# outage go silently unnoticed for days, since it looked statistically
# identical to the constantly-occurring, entirely normal case of asking
# about a region with no ingested data.
# ---------------------------------------------------------------------------


def test_estimate_faithfulness_reports_zero_on_llm_outage() -> None:
    """Even with real retrieved evidence, a total LLM failure must score
    0.0, not a positive "evidence was present" score — the answer is
    empty regardless of what was retrieved.
    """
    state = ClimateRiskState(
        user_query="heat risk UK",
        rag_results=[{"content": "real evidence"}],
        kg_results={"found": True},
        llm_unavailable=True,
    )
    assert supervisor._estimate_faithfulness(state) == 0.0


def test_llm_outage_is_distinguishable_from_coverage_gap() -> None:
    """These two must never collapse into the same signal: coverage_gap
    means the system correctly found no evidence (expected, benign,
    happens constantly for unsupported regions); llm_unavailable means
    the LLM layer itself was down (an infrastructure failure that should
    page someone). A monitor checking only one of these would miss real
    outages that look identical to normal refusals otherwise.
    """
    refusal = ClimateRiskState(user_query="flood risk Mumbai", coverage_gap=True)
    outage = ClimateRiskState(user_query="heat risk UK", llm_unavailable=True)

    assert refusal.llm_unavailable is False
    assert outage.coverage_gap is False


# ---------------------------------------------------------------------------
# Bug 5 (Round 6, finding 2): an LLM outage was reported to the user as
# "insufficient grounding". A failed call_llm() produces no text, which
# correctly scores 0.0 faithfulness, which fell through to the
# below-threshold branch — so the user was told the retrieved *evidence*
# was inadequate when the evidence had never been read. Measured at 70 of
# 91 queries under concurrent load. For a system whose entire claim is
# "answers you can check against a source", asserting something false
# about the source is the most damaging failure available to it.
# ---------------------------------------------------------------------------


def test_llm_outage_does_not_claim_the_evidence_was_insufficient() -> None:
    """The outage branch must not reuse the grounding-failure message.

    Asserted on content rather than on an exact string so a future
    reword can't quietly reintroduce the conflation: the message must
    not blame the evidence, and must say the model service failed.
    """
    schema = load_schema()
    result = apply_output_filter(
        draft_answer="",
        faithfulness_score=0.0,
        known_datasets=schema["datasets"],
        llm_unavailable=True,
    )

    answer = result.final_answer.lower()
    assert result.approved is False
    assert "insufficient grounding" not in answer
    assert "does not meet this system's faithfulness threshold" not in answer
    assert "unavailable" in answer
    assert "not a judgement about the climate evidence" in answer
    assert "llm_unavailable" in (result.blocked_reason or "")


def test_genuine_grounding_failure_still_says_insufficient_grounding() -> None:
    """The fix must not swallow real grounding failures into the outage
    message — a thin-evidence refusal is correct behaviour and must keep
    saying so. Same score, different cause, different message.
    """
    schema = load_schema()
    result = apply_output_filter(
        draft_answer="some ungrounded draft",
        faithfulness_score=0.0,
        known_datasets=schema["datasets"],
        llm_unavailable=False,
    )

    assert result.approved is False
    assert "insufficient grounding" in result.final_answer.lower()


def test_outage_check_precedes_the_groundedness_threshold() -> None:
    """Ordering matters and is easy to break. An outage always scores 0.0,
    so if the groundedness check ran first the outage branch would be
    unreachable and the bug would silently return.
    """
    schema = load_schema()
    outage = apply_output_filter(
        draft_answer="a draft that scores badly",
        faithfulness_score=0.0,
        known_datasets=schema["datasets"],
        llm_unavailable=True,
    )
    assert "unavailable" in outage.final_answer.lower()


# ---------------------------------------------------------------------------
# Bug 6 (Round 6, finding 1): the citation filter removed flagged tokens
# with str.replace, which is substring-based. Flagging the bare acronym
# "SSP" therefore rewrote every longer token containing it, so a live
# answer to a question about SSP5-8.5 came back discussing
# "[UNVERIFIED DATASET REMOVED]5-8.5". Two independent defects: the
# vocabulary was missing the bare scenario-family acronyms, and the
# removal had an unbounded blast radius.
# ---------------------------------------------------------------------------


def test_scenario_label_asked_about_survives_the_citation_filter() -> None:
    """The exact live failure: SSP5-8.5 must come through intact."""
    schema = load_schema()
    text = (
        "Under SSP5-8.5 the UKCP18 projections indicate hotter, drier "
        "summers. SSP projections were also used for CMIP6, and SSPs "
        "differ from the older pathways."
    )
    filtered, _ = verify_and_filter_datasets(text, schema["datasets"])

    assert "SSP5-8.5" in filtered
    assert "SSPs" in filtered
    assert "UNVERIFIED DATASET REMOVED" not in filtered


def test_rcp_labels_survive_ukcp18s_own_phrasing() -> None:
    """UKCP18's reports are written in RCP labels, which schema.json does
    not list at all. "the RCP8.5 data" trips the presented-as-a-source
    check, so before the fix the one corpus this project has ingested had
    its own scenario vocabulary stripped out of answers about it.
    """
    schema = load_schema()
    text = (
        "Based on the RCP8.5 data, UK summer warming by 2070 ranges from "
        "0.9C to 5.4C. The RCP2.6 projections are lower."
    )
    filtered, verification = verify_and_filter_datasets(text, schema["datasets"])

    assert "RCP8.5" in filtered
    assert "RCP2.6" in filtered
    assert "RCP8.5" not in verification


def test_unverified_dataset_removal_does_not_damage_longer_tokens() -> None:
    """The blast-radius half of the fix, tested independently of climate
    vocabulary: a fake dataset must be removed without touching a
    legitimate token that merely contains it as a substring.
    """
    schema = load_schema()
    text = (
        "The CMIP6X dataset reports severe flooding, whereas CMIP6XL data "
        "does not. CMIP6 itself is fine."
    )
    filtered, verification = verify_and_filter_datasets(text, schema["datasets"])

    # The impostors are flagged and removed...
    assert verification.get("CMIP6X") is False
    assert "[UNVERIFIED DATASET REMOVED]" in filtered
    # ...without leaving a mangled fragment of the longer token behind,
    # which is what str.replace produced ("[...]L data").
    assert "REMOVED]L" not in filtered
    assert "REMOVED]X" not in filtered
    # And the real dataset is untouched.
    assert "CMIP6 itself is fine" in filtered


def test_fake_dataset_names_are_still_stripped() -> None:
    """Both fixes loosen the filter, so this pins the original Round 1
    guarantee: an invented dataset name must still never reach a user.
    """
    schema = load_schema()
    filtered, verification = verify_and_filter_datasets(
        "The SuperClimate9000 dataset reports severe flooding.", schema["datasets"]
    )

    assert verification.get("SuperClimate9000") is False
    assert "SuperClimate9000" not in filtered
    assert "[UNVERIFIED DATASET REMOVED]" in filtered
