"""Unit tests for agents/analysis_agent.py: coverage-gap guard, missing
NetCDF path handling, and subprocess timeout enforcement.
"""

from __future__ import annotations

import pytest

from agents.analysis_agent import (
    _resolve_netcdf_path,
    _run_generated_code,
    run_analysis_agent,
)
from graph.state import ClimateRiskState


@pytest.mark.asyncio
async def test_analysis_agent_requires_valid_kg_result() -> None:
    state = ClimateRiskState(user_query="flood risk Kerala", kg_results={"found": False})
    result_state = await run_analysis_agent(state)
    assert result_state.analysis_results["success"] is False
    assert "valid KG result" in result_state.analysis_results["error"]


@pytest.mark.asyncio
async def test_analysis_agent_reports_missing_netcdf_path() -> None:
    # Uses a dataset name _resolve_netcdf_path never maps to a directory
    # (only "CMIP6"/"CORDEX" are), so this stays independent of whether
    # real NetCDF data happens to be configured on disk in this environment.
    state = ClimateRiskState(
        user_query="flood risk Kerala",
        kg_results={"found": True, "dataset": "UKCP18", "variable": "precipitation"},
    )
    result_state = await run_analysis_agent(state)
    assert result_state.analysis_results["success"] is False
    assert "NetCDF" in result_state.analysis_results["error"]


def test_resolve_netcdf_path_returns_none_for_unknown_dataset() -> None:
    assert _resolve_netcdf_path("UnknownDataset") is None


def test_run_generated_code_reports_timeout() -> None:
    slow_code = "import time\ntime.sleep(100)\n"
    import config

    original_timeout = config.ANALYSIS_TIMEOUT
    config.ANALYSIS_TIMEOUT = 1
    try:
        result = _run_generated_code(slow_code, "dummy.nc")
    finally:
        config.ANALYSIS_TIMEOUT = original_timeout
    assert result["success"] is False
    assert "timed out" in result["error"]


def test_run_generated_code_reports_bad_json() -> None:
    code = "print('not json')\n"
    result = _run_generated_code(code, "dummy.nc")
    assert result["success"] is False
