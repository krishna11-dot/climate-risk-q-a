"""Tests for tools/check_shared_concurrent_state.py: the standalone
AST-based check for the same mutable object being handed to two or more
concurrently-scheduled tasks without a copy (see MAINTENANCE.md Round 1,
bug #2, and the tool's own module docstring for why this exists instead
of a ruff rule).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

_CHECKER = str(Path(__file__).resolve().parent.parent.parent / "tools" / "check_shared_concurrent_state.py")


def _run_checker(source: str) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        path = f.name
    try:
        result = subprocess.run(
            [sys.executable, _CHECKER, path],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stdout
    finally:
        Path(path).unlink(missing_ok=True)


def test_flags_same_object_in_two_create_task_calls() -> None:
    code = (
        "import asyncio\n"
        "async def run_both(state):\n"
        "    a = asyncio.create_task(run_rag_agent(state))\n"
        "    b = asyncio.create_task(run_analysis_agent(state))\n"
        "    return await asyncio.gather(a, b)\n"
    )
    returncode, output = _run_checker(code)
    assert returncode == 1
    assert "'state'" in output


def test_flags_same_object_passed_directly_to_gather() -> None:
    code = (
        "import asyncio\n"
        "async def run_both(state):\n"
        "    return await asyncio.gather(run_rag_agent(state), run_analysis_agent(state))\n"
    )
    returncode, output = _run_checker(code)
    assert returncode == 1
    assert "'state'" in output


def test_does_not_flag_model_copy_at_each_call_site() -> None:
    code = (
        "import asyncio\n"
        "async def run_both(state):\n"
        "    a = asyncio.create_task(run_rag_agent(state.model_copy(deep=True)))\n"
        "    b = asyncio.create_task(run_analysis_agent(state.model_copy(deep=True)))\n"
        "    return await asyncio.gather(a, b)\n"
    )
    returncode, output = _run_checker(code)
    assert returncode == 0
    assert "No shared-mutable-concurrent-state issues found." in output


def test_does_not_flag_a_single_task_alone() -> None:
    code = (
        "import asyncio\n"
        "async def run_one(state):\n"
        "    return await asyncio.create_task(run_rag_agent(state))\n"
    )
    returncode, _ = _run_checker(code)
    assert returncode == 0


def test_does_not_flag_two_different_objects() -> None:
    code = (
        "import asyncio\n"
        "async def run_both(state_a, state_b):\n"
        "    a = asyncio.create_task(run_rag_agent(state_a))\n"
        "    b = asyncio.create_task(run_analysis_agent(state_b))\n"
        "    return await asyncio.gather(a, b)\n"
    )
    returncode, _ = _run_checker(code)
    assert returncode == 0
