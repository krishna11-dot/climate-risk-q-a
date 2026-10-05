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

# Deliberately says nothing about the evidence. Until 2026-10-05 an LLM
# outage returned _INSUFFICIENT_GROUNDING_MESSAGE, because a failed
# call_llm() produces no text and therefore scores 0.0 faithfulness —
# which told the user the *climate record* was too thin to answer when
# the real event was that both the primary and fallback models failed.
# Measured at 70 of 91 queries under concurrent load. For a system whose
# whole claim is answers traceable to a source, asserting something false
# about the source is the worst available failure, so this is now a
# separate message on a separate branch. See MAINTENANCE.md Round 6,
# finding 2.
_LLM_UNAVAILABLE_MESSAGE = (
    "No answer was generated: the language model service was unavailable "
    "(both the primary and fallback models failed). This is a system "
    "failure on our side, NOT a judgement about the climate evidence — "
    "the underlying data may be perfectly adequate and was not assessed. "
    "Please retry. If this persists, the system owner should check the "
    "LLM provider status and rate limits before any conclusion is drawn "
    "about data coverage."
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


# Emissions-scenario naming families that are legitimate climate
# vocabulary but are NOT datasets and must never be citation-controlled.
#
# `SSP` is derivable from schema.json's scenario list (the stem of
# "SSP5-8.5"), and is derived rather than hardcoded below. `RCP` is not
# in the schema at all, yet it is the vocabulary UKCP18's own reports are
# written in — which is exactly how this defect surfaced, on the one
# corpus this project has actually ingested.
#
# Listing RCP here deliberately does NOT assert that any RCP pathway is
# equivalent to any SSP pathway. That equivalence is a scientific
# judgement for the project owner, tracked separately; this set only
# says "these tokens are scenario vocabulary, not dataset claims," which
# is true regardless of how the pathways map to each other.
_SCENARIO_FAMILIES: frozenset[str] = frozenset({"RCP", "SSP"})


def _kg_vocabulary() -> set[str]:
    """Every term the knowledge graph legitimately knows about.

    Hazards, variables, scenarios and regions are valid things for an
    answer to name — only *datasets* are subject to citation control —
    so they must not be mistaken for unverified dataset citations.

    Includes the bare scenario-family acronyms (e.g. `SSP` from
    `SSP5-8.5`, plus `RCP`) as well as the full labels. Without them a
    phrase like "SSP projections" was read as a dataset citation, failed
    verification, and was stripped from the answer.

    Returns:
        Upper-cased set of all KG vocabulary terms.
    """
    schema = load_schema()
    vocabulary: set[str] = set()
    for key in ("hazards", "variables", "scenarios", "regions", "datasets"):
        vocabulary.update(str(term).upper() for term in schema.get(key, []))

    # Bare family acronyms derived from the full scenario labels, so a
    # new scenario added to schema.json needs no change here.
    vocabulary.update(
        stem for stem in (_alphabetic_stem(str(s)) for s in schema.get("scenarios", []))
        if stem
    )
    vocabulary.update(_SCENARIO_FAMILIES)
    return vocabulary


def _scenario_stems() -> set[str]:
    """Alphabetic prefixes of every known emissions-scenario family.

    Used to recognise *unlisted* members of a known family. Adding the
    bare acronym `RCP` to the vocabulary is not sufficient on its own:
    `RCP8.5` is a distinct token, is absent from schema.json, and shares
    no stem with any dataset — so without this it still reaches the
    "presented as a source" check and gets stripped on UKCP18's own
    phrasing ("the RCP8.5 projections").

    Returns:
        Upper-cased set of scenario-family stems, e.g. {"SSP", "RCP"}.
    """
    schema = load_schema()
    stems = {
        stem for stem in (_alphabetic_stem(str(s)) for s in schema.get("scenarios", []))
        if stem
    }
    return stems | set(_SCENARIO_FAMILIES)


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
    scenario_stems = _scenario_stems()

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
        if _alphabetic_stem(token) in scenario_stems:
            # An emissions scenario from a known family, listed or not
            # (RCP8.5, RCP2.6, SSP3-7.0). Scenario labels are never
            # dataset citations, so they are not citation-controlled.
            # Checked before the dataset-stem test below, which is
            # unreachable for these anyway, and before the
            # "presented as a source" test, which these DO trip on
            # UKCP18's natural phrasing.
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
            # Word-boundary substitution, NOT str.replace. A plain
            # str.replace is substring-based, so removing a short token
            # rewrote every longer token containing it: flagging "SSP"
            # turned "SSP5-8.5" into "[UNVERIFIED DATASET REMOVED]5-8.5"
            # and "SSPs" into "[UNVERIFIED DATASET REMOVED]s" — in a live
            # answer to a question that was *about* SSP5-8.5. The bug is
            # independent of climate vocabulary: any flagged short token
            # would take valid longer tokens with it. See MAINTENANCE.md
            # Round 6, finding 1.
            filtered_text = re.sub(
                rf"\b{re.escape(dataset)}\b",
                "[UNVERIFIED DATASET REMOVED]",
                filtered_text,
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
    llm_unavailable: bool = False,
) -> OutputFilterResult:
    """Runs the full output filter: LLM-availability check, groundedness
    threshold check, then dataset citation verification against the KG.

    Args:
        draft_answer: The draft answer text to filter.
        faithfulness_score: Faithfulness/groundedness score for the draft.
        known_datasets: All dataset names defined in the KG schema.
        llm_unavailable: True if both the primary and fallback model
            calls failed for this query. Must be checked BEFORE the
            groundedness threshold, because an outage always scores 0.0
            faithfulness and would otherwise be reported as a
            "the evidence is insufficient" refusal — a false statement
            about the data. Defaults to False so existing call sites
            keep their previous behavior rather than silently
            misreporting outages as grounding failures.

    Returns:
        An OutputFilterResult with the approved/rewritten answer.
    """
    if llm_unavailable:
        return OutputFilterResult(
            approved=False,
            final_answer=_LLM_UNAVAILABLE_MESSAGE,
            blocked_reason=(
                "llm_unavailable: primary and fallback model calls both "
                "failed; this is an infrastructure failure, not a "
                "grounding failure"
            ),
        )

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
