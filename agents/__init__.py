"""Agent package for the climate risk multi-agent system.

Shared LiteLLM call helper used by every agent, so model routing,
fallback, caching, and cost tracking are consistent across the stack.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import litellm

import config

logger = logging.getLogger(__name__)

if config.LITELLM_CACHE_ENABLED:
    litellm.cache = litellm.Cache()

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*\Z", re.DOTALL)


def _default_reasoning_effort(model: str) -> str | None:
    """Picks a sane default reasoning_effort for known reasoning models so
    hidden <think> tokens don't consume the whole output budget.

    Different providers accept different value sets for this parameter
    (Qwen3 accepts "none" to fully disable thinking; gpt-oss only accepts
    "low"/"medium"/"high" and errors on "none"), so this can't be a single
    constant passed blindly to every model.

    Args:
        model: The LiteLLM model string, e.g. "groq/qwen/qwen3.6-27b".

    Returns:
        A reasoning_effort value to pass, or None if the model isn't a
        known reasoning model that needs one, or the provider doesn't
        support the parameter at all (e.g. OpenRouter rejects it outright
        for models that Groq accepts it for).
    """
    if model.startswith("openrouter/"):
        return None
    if "qwen3" in model or "qwen3.6" in model:
        return "none"
    if "gpt-oss" in model:
        return "low"
    return None


def _strip_reasoning(text: str) -> str:
    """Strips visible <think>...</think> reasoning blocks that some models
    (e.g. Qwen3 reasoning variants) emit inline in the completion content.

    If the response was truncated mid-thought (max_tokens cut it off
    before the closing tag), the entire dangling <think> block is
    removed rather than surfaced as a pseudo-answer.

    Args:
        text: Raw completion content, possibly containing reasoning tags.

    Returns:
        The text with any reasoning block removed and whitespace trimmed.
    """
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _UNCLOSED_THINK_RE.sub("", cleaned)
    return cleaned.strip()


async def call_llm(
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 1000,
    **kwargs: Any,
) -> tuple[str, float]:
    """Calls an LLM via LiteLLM with automatic fallback and cost tracking.

    Args:
        model: Model name from config.py (never hardcoded at call sites).
        messages: Chat messages in OpenAI format.
        max_tokens: Maximum tokens to generate.
        **kwargs: Additional keyword args forwarded to litellm.acompletion.

    Returns:
        Tuple of (response_text, cost_usd). Both the text and cost are
        empty/zero if the primary call AND the fallback both fail — the
        pipeline is expected to treat empty evidence as ungrounded and
        respond via the groundedness guardrail rather than crash.
    """
    user_specified_effort = kwargs.pop("reasoning_effort", None)

    def _kwargs_for(target_model: str) -> dict[str, Any]:
        call_kwargs = dict(kwargs)
        effort = user_specified_effort if user_specified_effort is not None else _default_reasoning_effort(target_model)
        if effort is not None:
            call_kwargs["reasoning_effort"] = effort
        return call_kwargs

    response = None
    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            num_retries=config.LITELLM_MAX_RETRIES,
            **_kwargs_for(model),
        )
    except Exception as primary_exc:  # noqa: BLE001 - any provider failure falls back
        logger.warning("Primary model %s failed: %s", model, primary_exc)
        try:
            response = await litellm.acompletion(
                model=config.LITELLM_FALLBACK_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                num_retries=config.LITELLM_MAX_RETRIES,
                **_kwargs_for(config.LITELLM_FALLBACK_MODEL),
            )
        except Exception as fallback_exc:  # noqa: BLE001 - never crash the pipeline
            logger.error(
                "Fallback model %s also failed: %s", config.LITELLM_FALLBACK_MODEL, fallback_exc
            )
            return "", 0.0

    text = _strip_reasoning(response.choices[0].message.content or "")
    try:
        cost = litellm.completion_cost(completion_response=response)
    except Exception:  # noqa: BLE001 - cost tracking is best-effort
        cost = 0.0

    return text, cost
