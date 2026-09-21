"""LangSmith tracing setup and the shared @traceable decorator re-export.

Every agent function in agents/ is wrapped with @traceable so each step
of the pipeline is visible in LangSmith, which underpins the "explainable
to a regulator" guarantee and the online faithfulness-drift monitor.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar

import config

F = TypeVar("F", bound=Callable[..., Any])


def configure_langsmith() -> None:
    """Configures LangSmith environment variables from config.py.

    Call once at process startup (e.g. in main.py) before any traced
    function executes.
    """
    if config.LANGSMITH_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = config.LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = config.LANGSMITH_PROJECT or "climate-risk-agent"
        if config.LANGSMITH_ENDPOINT:
            os.environ["LANGCHAIN_ENDPOINT"] = config.LANGSMITH_ENDPOINT


def traceable(*args: Any, **kwargs: Any) -> Callable[[F], F]:
    """Wraps langsmith.traceable, falling back to a no-op decorator if
    LangSmith is not configured (e.g. in local unit tests without an
    API key), so agents remain fully testable offline.

    Returns:
        A decorator applying LangSmith tracing when available.
    """
    if config.LANGSMITH_API_KEY:
        from langsmith import traceable as _langsmith_traceable

        return _langsmith_traceable(*args, **kwargs)

    def _noop_decorator(func: F) -> F:
        return func

    if args and callable(args[0]) and not kwargs:
        return args[0]
    return _noop_decorator
