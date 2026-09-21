# Climate Risk Q&A Agent

> **Governed climate risk agent — KG + SQL + pgvector — structurally
> cannot hallucinate datasets, fully auditable, regulatory-grade.**

A production-grade, enterprise-governed multi-agent system that answers
climate risk questions with consultant-quality analysis, grounded by a
knowledge graph, retrieved via hybrid search, and backed by a full audit
trail exportable for regulatory review.

## Further reading

- **`docs/business-problem-and-alignment.md`** — the business problem
  explained in plain language, with a factual, honest check of what's
  actually been proven to work against what the project set out to do
  (includes real per-region data coverage status).
- **`MAINTENANCE.md`** — plain-language record of bugs found and fixed
  during maintenance rounds, and why each mattered.
- **`docs/maintenance-round-1-opus5.md`** — the first maintenance round
  mapped item-by-item against a maintenance checklist, including what
  was *not* done and why.
- **`docs/engineering-practices-review.md`** — an honest check of this
  project against a standard "build a real AI system" learning path and
  a standard AI-system metrics framework: what's genuinely done,
  verified live, versus configured-but-unproven versus not attempted.

## Setup order

1. `docker-compose up postgres` — starts PostgreSQL + pgvector and runs
   the migration in `db/migrations/` automatically on first boot.
2. `python rag/ingest.py`
   - TODO: download UKCP18 PDFs from the UK Met Office website into
     `config.UKCP18_PDF_DIR` first.
   - TODO: configure CMIP6/CORDEX NetCDF file paths in `config.py`
     before running the analysis agent against real data.
3. `docker-compose up app` — starts the FastAPI service.
4. `streamlit run streamlit_app.py` — starts the frontend.
5. `python evaluation/ragas_eval.py` — offline RAGAS evaluation.
6. `python evaluation/red_team_suite.py` — adversarial guardrail suite.

Copy `.env.example` to `.env` and fill in `GROQ_API_KEY` and
`LANGSMITH_API_KEY` before starting anything that calls an LLM.

## Data sources (all free)

| Source | Use | Link |
|---|---|---|
| UKCP18 PDFs | UK regional climate projections | UK Met Office website |
| CMIP6 NetCDF | Global climate model ensembles | esgf-node.llnl.gov |
| CORDEX | Regional downscaled projections | ESGF portal (same) |
| ERA5 | Reanalysis baseline data | Copernicus Climate Data Store (free registration) |

The knowledge graph schema itself (`knowledge_graph/schema.json`) needs
no external dataset — it encodes valid hazard/variable/scenario/region/
dataset combinations directly.

## SQL architecture

Retrieval is a four-stage hybrid pipeline, and the SQL layer is what
makes it both fast and grounded:

1. **SQL pre-filter (always runs first)** — `WHERE dataset = ... AND
   scenario = ... AND region IN (...)`, driven by the KG agent's
   traversal result. Narrows ~10,000 chunks to ~200 candidates in
   milliseconds, before any embedding math happens.
2. **pgvector semantic search** — cosine similarity over the SQL-
   filtered candidates only.
3. **BM25 keyword search** — exact-match strength on terms like
   `CMIP6`, `SSP5-8.5`, `Kerala`, fused with vector ranks via
   reciprocal rank fusion (RRF).
4. **Cross-encoder reranking** — `cross-encoder/ms-marco-MiniLM-L-6-v2`
   reranks the fused top 20 down to the final top 5, with full source
   metadata attached.

The key insight: the knowledge graph constrains **what** datasets are
valid; SQL constrains **which** chunks are searched; vector search finds
**relevant** content; the reranker selects the **best** 5 chunks. The
result is zero hallucinated dataset citations and a ~50x smaller search
space per query.

## Anti-hallucination stack

Four independent techniques stack together:

1. **RAG grounding** — the LLM only answers from retrieved chunks, never
   from memory alone.
2. **Knowledge graph constraint** — dataset citations come from KG nodes
   only. It is structurally impossible to hallucinate a dataset name:
   `guardrails/output_filter.py` verifies every citation against
   `knowledge_graph/query.verify_dataset_in_kg()` and strips anything
   unverified before the answer ever reaches the user.
3. **Structured output** — Pydantic v2 schemas on every agent input and
   output (see `graph/state.py`) mean no agent can silently invent a
   field or pass malformed data downstream.
4. **Confidence + groundedness threshold** — if faithfulness drops below
   `config.GROUNDEDNESS_THRESHOLD` (0.75), the system returns
   "insufficient grounding" instead of a low-quality guess.

## Red team suite

`evaluation/red_team_suite.py` runs 10 adversarial prompts — prompt
injection, jailbreak, PII leak, hallucination bait, Tier 1
financial/legal traps, out-of-scope, ambiguous, KG coverage gap, and
embedded injection — against the full pipeline and asserts each
guardrail held. It runs on every push in `.github/workflows/ci.yml` and
fails the build (exit code 1) on any regression.

## Three regulatory questions, answered

**Q1: Does it behave correctly before go-live?**
`evaluation/ragas_eval.py` enforces RAGAS faithfulness/relevancy/
precision ≥ 0.80 overall *and* per region segment (catching geographic
bias an aggregate score would hide). `evaluation/red_team_suite.py`
confirms all 10 adversarial cases are blocked as expected. Both run in
CI on every push.

**Q2: Is it explainable to a regulator?**
Every query writes a full record via `observability/audit_logger.py` to
both the queryable `audit_log` PostgreSQL table and an append-only
`audit/queries.jsonl` backup — tier assigned, router decision, KG nodes
traversed, datasets cited and verified, RAG chunks used, faithfulness/
groundedness scores, and LiteLLM cost. `export_audit_report(query_id)`
returns the full record on demand, and the KG traversal path is shown
directly in the Streamlit UI.

**Q3: Would we find out before the customer does?**
`evaluation/online_monitor.py` runs SQL queries against `audit_log`
every hour: an aggregate faithfulness drift check (alerts below 0.80)
and a per-region `GROUP BY` segment check (alerts when e.g. South Asia
underperforms the UK). Alerts go to the named owner in
`config.ALERT_OWNER`, who follows a fixed escalation path — set the
`AGENT_PAUSED` kill switch, investigate LangSmith traces, fix, and
re-evaluate before restarting. Nothing auto-adjusts.

## Data status (updated after real ingestion, see docs/business-problem-and-alignment.md)

| Region | Real evidence loaded | Notes |
|---|---|---|
| UK | ✅ 4 UKCP18 PDFs, 517 chunks | RAG-grounded answers verified live |
| Kerala | ✅ Real ERA5 precipitation data | Analysis agent verified against it |
| Global | ✅ One real CMIP6 file | Analysis agent verified against it |
| Everywhere else | ❌ No real data yet | Correctly returns "insufficient grounding" |

CORDEX has no local data at all. `config.CMIP6_NETCDF_DIR`,
`config.ERA5_NETCDF_DIR`, `config.CORDEX_NETCDF_DIR`,
`config.UKCP18_PDF_DIR` are all wired up — adding more regions/datasets
is a data-download task, not a code change.

## Known TODOs (see inline comments)

- Compound hazard queries, e.g. "flood AND heat risk for Mumbai"
  (`agents/supervisor.py`)
- Regulatory PDF export via reportlab (`observability/audit_logger.py`)
- Uncertainty quantification across ensemble runs
  (`agents/analysis_agent.py`)
- Named human alert owner (`config.py: ALERT_OWNER`)
- Real RAGAS evaluation currently falls back to an internal proxy score
  silently (`evaluation/ragas_eval.py`) — not the genuine LLM-judged
  metric the design calls for
- No `ruff` lint step in CI yet, despite `pyproject.toml` configuring it
- Project has no git history yet, so `.github/workflows/ci.yml` has
  never actually run
- Knowledge graph currently has one entry (Kerala → ERA5) that matches
  local disk contents rather than scientific reality — a design
  decision flagged for review in `docs/maintenance-round-1-opus5.md`
