"""Online production monitor: SQL-based faithfulness drift detection and
per-region segment monitoring against the audit_log table.

Never auto-adjusts anything. Alerts the named ALERT_OWNER in config.py,
who follows the documented escalation path (set AGENT_PAUSED, investigate
LangSmith traces, fix, re-eval before restart).
"""

from __future__ import annotations

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
