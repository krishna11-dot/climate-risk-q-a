"""Guardrail layer 3: output filtering.

Verifies every dataset cited in the final answer against the knowledge
graph (removing/flagging any that aren't verified), and enforces the
groundedness/faithfulness threshold: below config.GROUNDEDNESS_THRESHOLD
the system returns an "insufficient grounding" message instead of a
low-quality or potentially hallucinated answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import config
from knowledge_graph.builder import load_schema
from knowledge_graph.query import verify_dataset_in_kg

# Tokens that *look like* a climate dataset name: a capitalised word
# containing a digit (CMIP6, UKCP18, SuperClimate9000) or a run of three
# or more capitals (CORDEX, CHIRPS). Deliberately broad — it only
# produces candidates, which are then classified below.
_DATASET_SHAPED_RE = re.compile(
    r"\b[A-Z][A-Za-z]*\d[A-Za-z0-9.\-]*\b|\b[A-Z]{3,}[0-9]*\b"
)

# Phrasing that presents a token as a data source rather than merely
# mentioning it, e.g. "according to X", "X dataset", "based on X".
_CITATION_CONTEXT_TEMPLATE = (
    r"(?:according to|based on|sourced from|reported in|drawn from|per|using)\s+"
    r"(?:the\s+)?{token}\b"
    r"|\b{token}\s+(?:dataset|data|projections|reanalysis|archive|ensemble)"
)

_INSUFFICIENT_GROUNDING_MESSAGE = (
    "Insufficient grounding to answer confidently. The retrieved evidence "
    "does not meet this system's faithfulness threshold, so no answer is "
    "returned rather than risking a low-quality or ungrounded response."
)


@dataclass
class OutputFilterResult:
    """Result of output filtering.

    Attributes:
        approved: True if the answer passed all output checks.
        final_answer: The (possibly rewritten) answer to return.
        datasets_verified: Dict mapping cited dataset name -> bool
            verified-in-KG.
        blocked_reason: Reason the answer was blocked/rewritten, if any.
    """

    approved: bool
    final_answer: str
    datasets_verified: dict[str, bool] = field(default_factory=dict)
    blocked_reason: str | None = None


def _alphabetic_stem(token: str) -> str:
    """Returns the leading alphabetic part of a token, upper-cased.

    Used to spot impostors: "CMIP7" and "CMIP5" share the stem "CMIP"
    with the real "CMIP6", which is exactly the shape a hallucinated
    dataset name takes.

    Args:
        token: A dataset-shaped token, e.g. "CMIP7".

    Returns:
        The alphabetic prefix in upper case, e.g. "CMIP".
    """
    match = re.match(r"^[A-Za-z]*", token)
    return match.group(0).upper() if match else ""


def _kg_vocabulary() -> set[str]:
    """Every term the knowledge graph legitimately knows about.

    Hazards, variables, scenarios and regions are valid things for an
    answer to name — only *datasets* are subject to citation control —
    so they must not be mistaken for unverified dataset citations.

    Returns:
        Upper-cased set of all KG vocabulary terms.
    """
    schema = load_schema()
    vocabulary: set[str] = set()
    for key in ("hazards", "variables", "scenarios", "regions", "datasets"):
        vocabulary.update(str(term).upper() for term in schema.get(key, []))
    return vocabulary


def _is_presented_as_a_source(text_: str, token: str) -> bool:
    """Checks whether the answer frames a token as a data source.

    Args:
        text_: The draft answer text.
        token: The candidate token to test.

    Returns:
        True if the token appears in dataset-citation phrasing.
    """
    pattern = _CITATION_CONTEXT_TEMPLATE.format(token=re.escape(token))
    return re.search(pattern, text_, re.IGNORECASE) is not None


def _extract_candidate_dataset_mentions(text_: str, known_datasets: list[str]) -> list[str]:
    """Finds tokens the answer appears to cite as a dataset.

    Unlike a plain allowlist scan (which can only ever find names that
    are already valid, and so can never catch a hallucination), this
    returns both legitimate citations *and* suspect ones:

      - any known dataset name that appears at all;
      - any dataset-shaped token sharing an alphabetic stem with a known
        dataset but differing from it (CMIP7, CMIP5, UKCP09, ERA6);
      - any other dataset-shaped token explicitly presented as a source
        ("SuperClimate9000 dataset", "according to CHIRPS").

    Terms the KG legitimately knows (scenarios such as SSP5-8.5, regions,
    hazards) and unrelated acronyms merely mentioned in passing (NAO,
    GMST, RCP8.5) are not treated as dataset citations.

    Args:
        text_: The draft answer text.
        known_datasets: Dataset names defined in the KG schema.

    Returns:
        Deduplicated list of tokens to verify, in order of appearance.
    """
    known_upper = {d.upper() for d in known_datasets}
    known_stems = {_alphabetic_stem(d) for d in known_datasets}
    vocabulary = _kg_vocabulary()

    candidates: list[str] = []
    for token in _DATASET_SHAPED_RE.findall(text_):
        if token in candidates:
            continue
        token_upper = token.upper()

        if token_upper in known_upper:
            candidates.append(token)
            continue
        if token_upper in vocabulary:
            # A scenario/region/hazard the KG knows — not a dataset claim.
            continue
        if _alphabetic_stem(token) in known_stems:
            # Same family as a real dataset but not the real one.
            candidates.append(token)
            continue
        if _is_presented_as_a_source(text_, token):
            candidates.append(token)

    return candidates


def verify_and_filter_datasets(
    answer_text: str, known_datasets: list[str]
) -> tuple[str, dict[str, bool]]:
    """Verifies every dataset mentioned in the answer against the KG.
    Any dataset not verified is stripped from the text and flagged.

    Args:
        answer_text: The draft answer text from the analysis/supervisor step.
        known_datasets: All dataset names defined in the KG schema, used
            to detect mentions (verification itself still goes through
            knowledge_graph.query.verify_dataset_in_kg).

    Returns:
        Tuple of (filtered_answer_text, {dataset_name: verified_bool}).
    """
    mentioned = _extract_candidate_dataset_mentions(answer_text, known_datasets)
    verification: dict[str, bool] = {}
    filtered_text = answer_text

    for dataset in mentioned:
        verified = verify_dataset_in_kg(dataset)
        verification[dataset] = verified
        if not verified:
            filtered_text = filtered_text.replace(
                dataset, "[UNVERIFIED DATASET REMOVED]"
            )

    return filtered_text, verification


def check_groundedness(faithfulness_score: float) -> bool:
    """Checks whether a faithfulness/groundedness score clears the
    minimum threshold required to return an answer at all.

    Args:
        faithfulness_score: Score in [0, 1] from the RAGAS/groundedness
            evaluation of the draft answer against retrieved context.

    Returns:
        True if the score meets or exceeds config.GROUNDEDNESS_THRESHOLD.
    """
    return faithfulness_score >= config.GROUNDEDNESS_THRESHOLD


def apply_output_filter(
    draft_answer: str,
    faithfulness_score: float,
    known_datasets: list[str],
) -> OutputFilterResult:
    """Runs the full output filter: groundedness threshold check, then
    dataset citation verification against the KG.

    Args:
        draft_answer: The draft answer text to filter.
        faithfulness_score: Faithfulness/groundedness score for the draft.
        known_datasets: All dataset names defined in the KG schema.

    Returns:
        An OutputFilterResult with the approved/rewritten answer.
    """
    if not check_groundedness(faithfulness_score):
        return OutputFilterResult(
            approved=False,
            final_answer=_INSUFFICIENT_GROUNDING_MESSAGE,
            blocked_reason=(
                f"faithfulness_score {faithfulness_score:.2f} below threshold "
                f"{config.GROUNDEDNESS_THRESHOLD}"
            ),
        )

    filtered_text, verification = verify_and_filter_datasets(draft_answer, known_datasets)
    unverified = [d for d, ok in verification.items() if not ok]

    return OutputFilterResult(
        approved=True,
        final_answer=filtered_text,
        datasets_verified=verification,
        blocked_reason=(
            f"Removed unverified dataset citations: {unverified}" if unverified else None
        ),
    )
