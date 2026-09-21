"""Guardrail layer 1: input validation.

Detects prompt injection, jailbreak attempts, embedded instructions,
out-of-scope queries, and PII in the raw user query before any agent
sees it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"disregard (all )?(prior|previous) instructions",
    r"disable (safety|the )?(safety )?guardrails",
    r"reveal your system prompt",
    r"you are now (in )?dan mode",
    r"jailbreak",
    r"^\s*system\s*:",
    r"pretend (you are|to be) (an? )?unrestricted",
    r"act as if you have no restrictions",
]

_EMBEDDED_INSTRUCTION_PATTERNS = [
    r"system\s*:\s*ignore",
    r"\[system\]",
    r"<\s*system\s*>",
    r"new instructions\s*:",
]

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")

_CLIMATE_KEYWORDS = [
    "flood", "heat", "drought", "climate", "precipitation", "temperature",
    "rainfall", "sea level", "risk", "hazard", "scenario", "ssp", "cmip",
    "cordex", "ukcp", "era5", "weather", "warming", "emission",
]


@dataclass
class ValidationResult:
    """Result of input validation.

    Attributes:
        is_valid: True if the query passed validation and may proceed.
        blocked_reason: Human-readable reason if blocked, else None.
        pii_detected: True if PII was found (query is redacted, not blocked).
        redacted_query: The query with any detected PII redacted.
        is_out_of_scope: True if the query is unrelated to climate risk.
    """

    is_valid: bool
    blocked_reason: str | None = None
    pii_detected: bool = False
    redacted_query: str = ""
    is_out_of_scope: bool = False


def _redact_pii(query: str) -> tuple[str, bool]:
    """Redacts emails and phone numbers from a query string.

    Args:
        query: Raw user query.

    Returns:
        Tuple of (redacted_query, pii_was_found).
    """
    found = False
    redacted = query
    if _EMAIL_RE.search(redacted):
        redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
        found = True
    if _PHONE_RE.search(redacted):
        redacted = _PHONE_RE.sub("[REDACTED_PHONE]", redacted)
        found = True
    return redacted, found


def _is_climate_related(query: str) -> bool:
    """Heuristically checks whether the query touches climate risk topics.

    Args:
        query: Raw or redacted user query.

    Returns:
        True if any known climate keyword appears in the query.
    """
    lowered = query.lower()
    return any(keyword in lowered for keyword in _CLIMATE_KEYWORDS)


def validate_input(query: str) -> ValidationResult:
    """Runs the full input validation pipeline: injection/jailbreak
    detection, embedded instruction detection, PII redaction, and
    out-of-scope detection.

    Args:
        query: Raw user query text.

    Returns:
        A ValidationResult describing whether the query may proceed.
    """
    lowered = query.lower()

    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return ValidationResult(
                is_valid=False,
                blocked_reason="Detected prompt injection or jailbreak attempt.",
                redacted_query=query,
            )

    for pattern in _EMBEDDED_INSTRUCTION_PATTERNS:
        if re.search(pattern, lowered):
            return ValidationResult(
                is_valid=False,
                blocked_reason="Detected embedded instruction attempt in query.",
                redacted_query=query,
            )

    redacted_query, pii_found = _redact_pii(query)

    if not _is_climate_related(redacted_query):
        return ValidationResult(
            is_valid=False,
            blocked_reason="Query is out of scope for climate risk analysis.",
            pii_detected=pii_found,
            redacted_query=redacted_query,
            is_out_of_scope=True,
        )

    return ValidationResult(
        is_valid=True,
        pii_detected=pii_found,
        redacted_query=redacted_query,
    )
