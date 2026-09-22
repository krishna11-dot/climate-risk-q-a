# Climate Risk Q&A Agent

> **Governed climate risk agent — KG + SQL + pgvector — structurally
> cannot hallucinate datasets, fully auditable.**

A multi-agent system, designed to enterprise assurance patterns, that
answers climate risk questions grounded by a knowledge graph, retrieved
via hybrid search, and backed by a full audit trail exportable for
regulatory review.

**Enterprise-designed, not yet enterprise-ready.** The architecture
follows the right patterns (four guardrail layers, tier authority, a
knowledge-graph anti-hallucination gate, evals in CI), and the core
grounding/refusal behavior is proven live with real data. But it hasn't
been proven to work *at* that standard yet: no API authentication, real
RAGAS scores are below their own 0.80 gate, it's never been load-tested,
and it's had exactly one human-plus-AI review pass, not an external one.
See "Known gaps" below for the specific, current list.

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
- **`docs/deslopify-in-plain-language.md`** — what a maintenance round
  ("deslopify") is and what each of the three rounds on this project
  actually found and fixed, explained for a general audience with no
  unexplained jargon.

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
5. Offline RAGAS evaluation (two phases, two separate venvs — see
   "Real RAGAS evaluation" below for why):
   `./.venv/Scripts/python.exe evaluation/generate_eval_records.py`
   then `./.venv-ragas/Scripts/python.exe evaluation/score_eval_records.py`.
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
`evaluation/generate_eval_records.py` (main venv) + `evaluation/
score_eval_records.py` (isolated `.venv-ragas`) enforce RAGAS
faithfulness/relevancy/precision ≥ 0.80 overall *and* per region segment
(catching geographic bias an aggregate score would hide) — see "Real
RAGAS evaluation" below for the actual current numbers, which are below
threshold. `evaluation/red_team_suite.py` confirms all 10 adversarial
cases are blocked as expected. Both run in CI on every push (RAGAS
scoring runs as a separate CI job — see `.github/workflows/ci.yml` —
because it needs its own dependency set, pinned in
`requirements-ragas.txt`).

**Q2: Is it explainable to a regulator?**
Every query writes a full record via `observability/audit_logger.py` to
both the queryable `audit_log` PostgreSQL table and an append-only
`audit/queries.jsonl` backup — tier assigned, router decision, KG nodes
traversed, datasets cited and verified, RAG chunks used, faithfulness/
groundedness scores, and LiteLLM cost. `export_audit_report(query_id)`
returns the full record on demand, and the KG traversal path is shown
directly in the Streamlit UI.

**Q3: Would we find out before the customer does?**
`evaluation/online_monitor.py` runs three SQL-based checks against
`audit_log`: an LLM-outage check (alerts on even one query where both
the primary and fallback model failed — distinct from a normal
"insufficient grounding" refusal, see `MAINTENANCE.md` Round 4), an
aggregate faithfulness drift check (alerts below 0.80), and a per-region
`GROUP BY` segment check (alerts when e.g. South Asia underperforms the
UK). Alerts go to the named owner in `config.ALERT_OWNER`, who follows a
fixed escalation path — set the `AGENT_PAUSED` kill switch, investigate
LangSmith traces, fix, and re-evaluate before restarting. Nothing
auto-adjusts. **Honest caveat:** running it (`python
evaluation/online_monitor.py`) executes all three checks once; nothing
currently schedules that to happen automatically on any cadence — that's
a deployment step (cron, a cloud scheduler, etc.), not something the
script does by itself yet.

## Real RAGAS evaluation

RAGAS's dependency chain (an older `langchain-community`) conflicts
directly with the versions `langgraph`/`litellm` need in production, so
it runs in its own venv (`.venv-ragas`, pinned in
`requirements-ragas.txt`) in two phases: `generate_eval_records.py`
(main venv, runs the real pipeline) writes `evaluation/eval_records.json`,
then `score_eval_records.py` (`.venv-ragas`) scores it with genuine
LLM-judged metrics — reusing the project's existing Groq/LiteLLM setup
as the judge, no separate provider.

Actual scores from the last real run against `evaluation/test_dataset.json`
(10 questions; only 2 — London, UK — had any retrieved context, since
those are the only regions with real ingested data; the other 8
correctly returned "insufficient grounding" and are excluded from
scoring):

| Metric | Score | Threshold | Note |
|---|---|---|---|
| Faithfulness (overall) | 0.778 | 0.80 | London 1.0, UK 0.556 — the UK answer makes at least one claim its retrieved chunks don't fully support |
| Answer relevancy | 0.473 | 0.80 | Genuinely mediocre — answers are faithful but not tightly on-topic |
| Context precision | 0.0 | 0.80 | Not a real signal yet — needs a genuine reference answer per question; `test_dataset.json` only has placeholder `pass`/`fail` labels |

Below threshold on two of three metrics — this is the system's real,
current quality level, not a placeholder or a bug in the eval script.

## Data status (updated after real ingestion, see docs/business-problem-and-alignment.md)

| Region | Real evidence loaded | Notes |
|---|---|---|
| UK | ✅ 4 UKCP18 PDFs, 517 chunks | RAG-grounded answers verified live |
| Kerala | ✅ Real ERA5 precipitation data | Analysis agent verified against it. **Caveat:** ERA5 is historical reanalysis data, not a future-scenario projection — the knowledge graph's `SSP5-8.5` label on this entry is a scenario tag of convenience, not a claim that the returned numbers are scenario-modelled. See `MAINTENANCE.md` backlog item 1 |
| Global | ✅ One real CMIP6 file | Analysis agent verified against it |
| Everywhere else | ❌ No real data yet | Correctly returns "insufficient grounding" |

CORDEX has no local data at all. `config.CMIP6_NETCDF_DIR`,
`config.ERA5_NETCDF_DIR`, `config.CORDEX_NETCDF_DIR`,
`config.UKCP18_PDF_DIR` are all wired up — adding more regions/datasets
is a data-download task, not a code change.

## Known gaps toward production/enterprise-ready

The design-vs-ready distinction above, made specific. See
`MAINTENANCE.md` for the full history of what's already been found and
fixed across four maintenance rounds — this list is what's still open:

- **No API authentication** — anyone who can reach the FastAPI endpoint
  can use it.
- **Answer quality is below its own gate** — real RAGAS scores are
  0.778 faithfulness / 0.473 relevancy against a 0.80 target (see "Real
  RAGAS evaluation" above). This needs prompt/retrieval tuning, not a
  bug fix.
- **Never load-tested** — no concurrent-user testing has been done.
- **CI has never completed a real run** — the repo has git history and
  is pushed, but the `GROQ_API_KEY` GitHub Actions secret still needs to
  be configured before a push produces a real (non-immediately-failing)
  CI run.
- **One reviewed-and-accepted scientific trade-off**: the knowledge
  graph's Kerala entry uses ERA5 (historical data) under a scenario
  label it doesn't strictly represent — a deliberate, documented
  decision (see Data status above and `MAINTENANCE.md` backlog item 1),
  not an oversight.
- **Named human alert owner** — `config.py: ALERT_OWNER` is a
  placeholder; this is a business decision, not a code task.
- Future feature work, not yet started: compound hazard queries (e.g.
  "flood AND heat risk for the UK"), regulatory PDF export
  (`observability/audit_logger.py`), uncertainty quantification across
  ensemble runs (`agents/analysis_agent.py`).
