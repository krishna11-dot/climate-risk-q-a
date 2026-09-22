-- Migration: add llm_unavailable to audit_log.
-- Idempotent: safe to re-run via IF NOT EXISTS guard.
--
-- Context: a total LLM failure (both primary and fallback model calls
-- failing, e.g. a provider silently renaming a model) previously looked
-- identical in the audit trail to a correct "insufficient grounding"
-- refusal — both produced an empty final_answer with nothing to tell
-- them apart. That let a real outage go unnoticed for days. This column
-- makes the distinction queryable so evaluation/online_monitor.py can
-- alert on it immediately, separately from the slower faithfulness-drift
-- average check.

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS llm_unavailable BOOLEAN NOT NULL DEFAULT FALSE;
