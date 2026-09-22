-- Migration: add faithfulness_measured to audit_log.
-- Idempotent: safe to re-run via IF NOT EXISTS guard.
--
-- Context: audit_log.faithfulness has always been populated by a fast
-- online proxy (presence of grounded evidence), not the real LLM-judged
-- RAGAS faithfulness metric computed offline in
-- evaluation/score_eval_records.py. Nothing distinguished the two, so a
-- regulator reading export_audit_report() output would reasonably read
-- `faithfulness` as a measured quantity. This column makes that
-- distinction explicit and queryable. Defaults to FALSE since every
-- existing row (and the current online per-query path) is a proxy.

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS faithfulness_measured BOOLEAN NOT NULL DEFAULT FALSE;
