"""Load test: fires concurrent queries at the running FastAPI service and
reports latency percentiles, throughput, and errors broken down by type.

The goal is to find where the system breaks, not to show that it is fast.
A run where nothing fails has only shown that concurrency was too low.

Why errors are classified rather than counted: there are at least four
distinct failure modes behind POST /query, and they need completely
different fixes — a provider rate limit wants a paid tier, pool
exhaustion wants a bigger DB_POOL_MAX_SIZE, an analysis timeout wants
subprocess warm-up work, and llm_unavailable means both the primary and
fallback model failed (an outage, not a refusal). An aggregate "7% error
rate" cannot distinguish them, so this script never reports one.

Quality degradation counts as a finding too: the embedder and
cross-encoder run in-process and compete for CPU with every concurrent
request, so this records refusal/insufficient-grounding rates alongside
the HTTP outcomes. A load test that logged only status codes would miss
retrieval getting worse under load, which is the thing most likely to
actually happen here.

Usage:
    python evaluation/load_test.py                      # default ramp
    python evaluation/load_test.py --concurrency 1,2,4  # explicit ramp
    python evaluation/load_test.py --requests 8 --url http://localhost:8000

Note on TTFT/ITL: this service does not stream (main.py returns one JSON
object after the whole pipeline completes), so time-to-first-token is
identical to total latency and inter-token latency does not exist. They
are deliberately not reported rather than reported as zero.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Queries span the tiers and routing branches on purpose: a load profile
# made only of answerable UK questions would never exercise the refusal,
# tier-1 and out-of-scope paths that real traffic hits.
DEFAULT_QUERIES: list[str] = [
    "What is the heat risk for the UK under SSP5-8.5?",
    "How will heat risk change for London under SSP2-4.5?",
    "What does UKCP18 say about summer temperature change in the UK?",
    "What is the projected flood risk for Kerala under SSP5-8.5?",
    "What is the drought risk for South Asia under SSP2-4.5?",
    "What is the flood risk for Antarctica under SSP5-8.5?",
    "Should I buy climate insurance for my Mumbai property?",
    "Tell me about risk",
]


@dataclass
class Outcome:
    """One request's result.

    Attributes:
        query: The question sent.
        latency_s: Wall-clock seconds from send to full response.
        http_status: HTTP status code, or None if the request never
            completed (connection error / client timeout).
        failure_mode: Classified failure label, or None on success.
        answer_class: Coarse classification of the answer body, used to
            spot quality degradation that a status code would hide.
        detail: Short diagnostic string for the report.
    """

    query: str
    latency_s: float
    http_status: int | None
    failure_mode: str | None
    answer_class: str
    detail: str = ""


@dataclass
class LevelResult:
    """Aggregated results for one concurrency level.

    Attributes:
        concurrency: Number of requests fired simultaneously.
        wall_s: Wall-clock seconds for the whole batch.
        outcomes: Individual request outcomes.
    """

    concurrency: int
    wall_s: float
    outcomes: list[Outcome] = field(default_factory=list)


def _classify_failure(status: int | None, body: dict[str, Any] | None, err: str) -> str | None:
    """Maps a response to one of this system's distinct failure modes.

    Args:
        status: HTTP status code, or None if the request never completed.
        body: Parsed JSON response body, if any.
        err: Client-side error text, if any.

    Returns:
        A failure-mode label, or None if the request succeeded.
    """
    lowered = err.lower()
    if status is None:
        if "timeout" in lowered or "timed out" in lowered:
            return "client_timeout"
        if "connection" in lowered or "refused" in lowered:
            return "connection_error"
        return f"client_error:{err[:60]}" if err else "client_error"

    if status == 429:
        return "http_429_rate_limited"
    if status >= 500:
        return f"http_{status}_server_error"
    if status != 200:
        return f"http_{status}"

    if not body:
        return "empty_body"

    # A 200 can still carry a real infrastructure failure: llm_unavailable
    # means both the primary and the fallback model call failed. The
    # pipeline deliberately does not crash on that (see call_llm), which
    # is exactly why it has to be surfaced here rather than counted as a
    # success.
    if body.get("llm_unavailable") is True:
        return "llm_unavailable_both_models_failed"
    if body.get("status") == "paused":
        return "agent_paused"
    if body.get("error"):
        return f"pipeline_error:{str(body['error'])[:60]}"
    return None


def _classify_answer(body: dict[str, Any] | None) -> str:
    """Coarsely classifies the answer body so quality degradation under
    load is visible alongside the error counts.

    Args:
        body: Parsed JSON response body, if any.

    Returns:
        A short answer-class label.
    """
    if not body:
        return "none"

    answer = (body.get("final_answer") or "").lower()
    if not answer:
        return "empty_answer"
    # Must precede the generic fall-through to "answered". The outage
    # message is prose like any other answer, so without this check a
    # run of total outages was reported as successfully answered — the
    # same class of blind spot that made the pre-fix load test report
    # "0 failures" through a 77% failure rate, reproduced in this script.
    if "the language model service was unavailable" in answer:
        return "failed_llm_unavailable"
    if "insufficient grounding" in answer:
        return "refused_insufficient_grounding"
    if "no verified climate dataset covers" in answer:
        return "refused_coverage_gap"
    if "requires human expert review" in answer:
        return "blocked_tier_1"
    if "out of scope" in answer:
        return "blocked_out_of_scope"
    if "too broad to answer" in answer:
        return "clarification_requested"
    if "prompt injection" in answer or "embedded instruction" in answer:
        return "blocked_injection"
    if "[unverified dataset removed]" in answer:
        # Not an error, but a known defect worth counting: see
        # MAINTENANCE.md backlog item 6.
        return "answered_with_stripped_citation"
    return "answered"


async def _one_request(
    session: Any, url: str, query: str, timeout_s: float
) -> Outcome:
    """Fires a single POST /query and classifies the result.

    Args:
        session: An aiohttp ClientSession.
        url: Base service URL.
        query: The question to send.
        timeout_s: Per-request client timeout in seconds.

    Returns:
        The classified Outcome.
    """
    import aiohttp

    started = time.perf_counter()
    status: int | None = None
    body: dict[str, Any] | None = None
    err = ""
    try:
        async with session.post(
            f"{url.rstrip('/')}/query",
            json={"query": query},
            timeout=aiohttp.ClientTimeout(total=timeout_s),
        ) as response:
            status = response.status
            text_body = await response.text()
            try:
                body = json.loads(text_body)
            except json.JSONDecodeError:
                err = f"non-json body: {text_body[:80]}"
    except Exception as exc:  # noqa: BLE001 - every client failure is a datapoint
        err = f"{type(exc).__name__}: {exc}"

    latency = time.perf_counter() - started
    return Outcome(
        query=query,
        latency_s=latency,
        http_status=status,
        failure_mode=_classify_failure(status, body, err),
        answer_class=_classify_answer(body),
        detail=err,
    )


async def run_level(
    url: str, queries: list[str], concurrency: int, total: int, timeout_s: float
) -> LevelResult:
    """Sends `total` requests while holding at most `concurrency` in flight.

    Concurrency is bounded by a semaphore rather than by the batch size,
    so the *workload* can be held identical across levels while only the
    in-flight limit changes. That separation matters: an earlier version
    of this script fired the whole batch at once, which made `total` and
    `concurrency` the same number and produced four runs of the same test
    instead of a concurrency curve.

    Args:
        url: Base service URL.
        queries: Query pool, cycled to fill the workload.
        concurrency: Maximum requests in flight at any moment.
        total: Total requests to send at this level.
        timeout_s: Per-request client timeout in seconds.

    Returns:
        A LevelResult for this concurrency level.
    """
    import aiohttp

    batch = [queries[i % len(queries)] for i in range(total)]
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(session: Any, query: str) -> Outcome:
        async with semaphore:
            return await _one_request(session, url, query, timeout_s)

    started = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        outcomes = await asyncio.gather(*(_bounded(session, q) for q in batch))
    return LevelResult(
        concurrency=concurrency,
        wall_s=time.perf_counter() - started,
        outcomes=list(outcomes),
    )


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile.

    Deliberately not interpolated: at the small sample sizes a free-tier
    load test can afford, an interpolated P99 invents a number that no
    request actually produced. Nearest-rank always reports a real
    observation.

    Args:
        values: Observed values.
        pct: Percentile in [0, 100].

    Returns:
        The percentile value, or 0.0 for an empty input.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round((pct / 100.0) * len(ordered) + 0.5) - 1))
    return ordered[rank]


def report(levels: list[LevelResult]) -> dict[str, Any]:
    """Prints and returns the load-test report.

    Args:
        levels: Results per concurrency level, in ramp order.

    Returns:
        The report as a JSON-serialisable dict.
    """
    summary: list[dict[str, Any]] = []

    print("\n" + "=" * 78)
    print("LOAD TEST REPORT")
    print("=" * 78)

    for level in levels:
        latencies = [o.latency_s for o in level.outcomes]
        ok = [o for o in level.outcomes if o.failure_mode is None]
        failures: dict[str, int] = {}
        for o in level.outcomes:
            if o.failure_mode:
                failures[o.failure_mode] = failures.get(o.failure_mode, 0) + 1
        answers: dict[str, int] = {}
        for o in level.outcomes:
            answers[o.answer_class] = answers.get(o.answer_class, 0) + 1

        n = len(level.outcomes)
        row = {
            "concurrency": level.concurrency,
            "requests": n,
            "wall_s": round(level.wall_s, 2),
            "succeeded": len(ok),
            "failed": n - len(ok),
            "throughput_rps": round(n / level.wall_s, 3) if level.wall_s else 0.0,
            "latency_s": {
                "min": round(min(latencies), 2) if latencies else 0.0,
                "p50": round(_percentile(latencies, 50), 2),
                "p95": round(_percentile(latencies, 95), 2),
                "p99": round(_percentile(latencies, 99), 2),
                "max": round(max(latencies), 2) if latencies else 0.0,
                "mean": round(statistics.fmean(latencies), 2) if latencies else 0.0,
            },
            "failures_by_type": failures,
            "answer_classes": answers,
        }
        summary.append(row)

        print(f"\n--- concurrency {level.concurrency} "
              f"({n} requests in {level.wall_s:.1f}s) ---")
        print(f"  succeeded      : {len(ok)}/{n}")
        print(f"  throughput     : {row['throughput_rps']} req/s")
        lat = row["latency_s"]
        print(f"  latency (s)    : p50={lat['p50']}  p95={lat['p95']}  "
              f"p99={lat['p99']}  min={lat['min']}  max={lat['max']}")
        if failures:
            print("  failures by type:")
            for mode, count in sorted(failures.items(), key=lambda kv: -kv[1]):
                print(f"      {count:>3}  {mode}")
        else:
            print("  failures by type: none")
        print("  answer classes :")
        for cls, count in sorted(answers.items(), key=lambda kv: -kv[1]):
            print(f"      {count:>3}  {cls}")

    print("\n" + "=" * 78)
    total = sum(len(lv.outcomes) for lv in levels)
    total_failed = sum(
        1 for lv in levels for o in lv.outcomes if o.failure_mode is not None
    )
    print(f"TOTAL: {total} requests, {total_failed} failed")
    if total_failed == 0:
        print("No failures at any level tested — concurrency was not pushed high")
        print("enough to find the breaking point. Raise --concurrency.")
    print("=" * 78 + "\n")

    return {"levels": summary, "total_requests": total, "total_failed": total_failed}


async def main() -> None:
    """Parses arguments, runs the concurrency ramp, writes the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument(
        "--concurrency",
        default="1,2,4",
        help="Comma-separated ramp, e.g. 1,2,4,8. Each level runs to completion.",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=0,
        help=(
            "Total requests per level, independent of the in-flight limit. "
            "Hold this fixed across the ramp so only concurrency varies — "
            "otherwise the workload changes with the level and the answer "
            "classes are not comparable between levels. Default: equal to "
            "the concurrency value."
        ),
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument(
        "--out",
        default="evaluation/load_test_results.json",
        help="Where to write the JSON report.",
    )
    args = parser.parse_args()

    ramp = [int(c) for c in args.concurrency.split(",") if c.strip()]
    levels: list[LevelResult] = []

    print(f"Target: {args.url}   ramp: {ramp}   per-request timeout: {args.timeout}s")

    for concurrency in ramp:
        count = args.requests or concurrency
        print(f"\n>>> {count} requests, max {concurrency} in flight ...")
        level = await run_level(
            args.url, DEFAULT_QUERIES, concurrency, count, args.timeout
        )
        levels.append(level)
        failed = sum(1 for o in level.outcomes if o.failure_mode)
        print(f"<<< done in {level.wall_s:.1f}s — {failed}/{count} failed")

    result = report(levels)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
