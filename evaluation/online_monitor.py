"""Online production monitor: SQL-based faithfulness drift detection,
per-region segment monitoring, and LLM-outage detection against the
audit_log table.

Never auto-adjusts anything. Alerts the named ALERT_OWNER in config.py,
who follows the documented escalation path (set AGENT_PAUSED, investigate
LangSmith traces, fix, re-eval before restart).

This module previously had no way to actually be run — no scheduler, no
entrypoint — despite README.md's claim that it "runs every hour." Running
it (`python evaluation/online_monitor.py`) now executes all three checks
once; wiring that into an actual hourly schedule (cron, a cloud
scheduler, etc.) is still a deployment step, not something this file can
do by itself.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

import config
from db.connection import get_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_recent_faithfulness_drift(window_hours: int = 1) -> dict:
    """Checks average faithfulness over the recent window against the
    0.80 drift threshold.

    Args:
        window_hours: Size of the trailing window to check, in hours.

    Returns:
        Dict with avg_faithfulness, alert (bool), and window_hours.
    """
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT AVG(faithfulness) AS avg_faithfulness, COUNT(*) AS n
                FROM audit_log
                WHERE timestamp > NOW() - make_interval(hours => :window_hours)
                  AND faithfulness IS NOT NULL
                """
            ),
            {"window_hours": window_hours},
        )
        row = result.mappings().one()

    avg_faithfulness = row["avg_faithfulness"]
    alert = avg_faithfulness is not None and avg_faithfulness < 0.80

    if alert:
        _fire_alert(
            f"Faithfulness drift: avg={avg_faithfulness:.3f} over last "
            f"{window_hours}h ({row['n']} queries), below 0.80 threshold."
        )

    return {
        "avg_faithfulness": avg_faithfulness,
        "n_queries": row["n"],
        "alert": alert,
        "window_hours": window_hours,
    }


async def check_llm_outage(window_minutes: int = 15) -> dict:
    """Checks for any query in the recent window where both the primary
    and fallback LLM calls failed — a real infrastructure outage, not a
    normal "insufficient grounding" refusal (see graph/state.py's
    llm_unavailable docstring for why the two must never be conflated).

    Unlike the faithfulness drift check, this alerts on ANY occurrence
    in the window rather than an average dropping below a threshold —
    a total LLM failure should never happen silently even once, whereas
    faithfulness naturally varies query to query.

    Args:
        window_minutes: Size of the trailing window to check, in minutes.

    Returns:
        Dict with n_failures, alert (bool), and window_minutes.
    """
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT COUNT(*) AS n
                FROM audit_log
                WHERE timestamp > NOW() - make_interval(mins => :window_minutes)
                  AND llm_unavailable IS TRUE
                """
            ),
            {"window_minutes": window_minutes},
        )
        row = result.mappings().one()

    n_failures = row["n"]
    alert = n_failures > 0

    if alert:
        _fire_alert(
            f"LLM outage detected: {n_failures} quer{'y' if n_failures == 1 else 'ies'} "
            f"in the last {window_minutes} minutes had both the primary and "
            f"fallback model calls fail. This is an infrastructure failure, "
            f"not a normal refusal — investigate immediately."
        )

    return {
        "n_failures": n_failures,
        "alert": alert,
        "window_minutes": window_minutes,
    }


async def check_segment_faithfulness() -> list[dict]:
    """Checks average faithfulness per region segment, catching
    geographic bias (e.g. South Asia underperforming vs UK) that an
    aggregate metric would hide.

    Returns:
        List of dicts, one per region below threshold, each with
        region, avg_faithfulness, and n_queries.
    """
    async with get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT region, AVG(faithfulness) AS avg_faithfulness, COUNT(*) AS n
                FROM audit_log
                WHERE faithfulness IS NOT NULL AND region IS NOT NULL
                GROUP BY region
                HAVING AVG(faithfulness) < :threshold
                """
            ),
            {"threshold": config.FAITHFULNESS_SEGMENT_THRESHOLD},
        )
        rows = result.mappings().all()

    underperforming = [dict(row) for row in rows]
    for row in underperforming:
        _fire_alert(
            f"Region '{row['region']}' faithfulness={row['avg_faithfulness']:.3f} "
            f"below segment threshold {config.FAITHFULNESS_SEGMENT_THRESHOLD} "
            f"({row['n']} queries)."
        )
    return underperforming


def _fire_alert(message: str) -> None:
    """Logs an alert addressed to the named ALERT_OWNER. Never auto-
    adjusts system behavior — a human must act via the escalation path.

    Args:
        message: The alert message describing the drift/bias detected.
    """
    owner = config.ALERT_OWNER
    logger.error(
        "ALERT for %s: %s | Escalation path: %s",
        owner["name"],
        message,
        owner["escalation_path"],
    )


async def run_all_checks() -> None:
    """Runs every monitoring check once and logs the results.

    Intended to be invoked on a schedule (cron, a cloud scheduler, etc.)
    — this function itself does not loop or sleep.
    """
    outage = await check_llm_outage()
    drift = await check_recent_faithfulness_drift()
    segments = await check_segment_faithfulness()
    logger.info(
        "Monitor run complete: outage=%s, drift=%s, underperforming_segments=%d",
        outage, drift, len(segments),
    )


if __name__ == "__main__":
    asyncio.run(run_all_checks())
