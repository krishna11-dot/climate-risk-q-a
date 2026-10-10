# Climate Risk Q&A Agent

> **Governed climate risk agent — KG + SQL + pgvector — structurally
> cannot hallucinate datasets, fully auditable.**

## The problem this solves

**Make climate information usable by people who aren't climate
specialists, with answers they can check against a source.**

The user is **anyone who needs sourced climate information for planning
but lacks specialist support** — a local-authority planner, a risk
analyst at a mid-size insurer, an NGO programme officer, a
sustainability lead writing a disclosure. Not climate scientists: they
already have the raw data and would find these guardrails an obstacle.

This is the problem described in **Williams et al.** — there aren't
enough climate specialists, UKCP18 is hard to use without help, and a
plain chatbot over that data can invent things. This project is a
governed answer to the same problem, on the same dataset their chatbot
uses, with the inventing designed out rather than warned about.

**Scope is the UK, deliberately.** UKCP18 is ingested and is the one
region proven end-to-end with real government data. Breadth across
regions is a data-loading task; the mechanism is what transfers.

**The return is capacity, not cost savings.** The constraint in the
problem above is that specialists are *scarce*, not that they are
expensive — so the comparison for most of these questions is against no
analysis at all, not against a cheaper expert. That makes traceability
an admissibility condition rather than a feature: an answer a planner
can't check is unusable, not merely weaker. Full reasoning and the ROI
model in `docs/business-problem-and-alignment.md`.

## What it is

A multi-agent system, designed to enterprise assurance patterns, that
answers climate risk questions grounded by a knowledge graph, retrieved
via hybrid search, and backed by a full audit trail exportable for
regulatory review.

**Enterprise-designed, not yet enterprise-ready.** The architecture
follows the right patterns (four guardrail layers, tier authority, a
knowledge-graph anti-hallucination gate, evals in CI), and the pipeline
genuinely works end to end on real UK government data: 517 UKCP18 chunks
ingested, KG traversal, hybrid retrieval, and a complete audit trail per
query — all verified live on 2026-10-05.

**It was run under load for the first time on 2026-10-05, and that
changed this list.** Under concurrency the system converts answerable
questions into refusals, because Groq's free-tier token limit takes the
LLM down and the user-facing message blames the *evidence* instead:
measured, 70 of 91 logged queries were in total LLM outage and every one
returned "insufficient grounding," at HTTP 200. Separately, the
anti-hallucination filter strips the string `SSP` by substring, so a
question about `SSP5-8.5` gets an answer about
`[UNVERIFIED DATASET REMOVED]5-8.5`. Still open besides those: no API
authentication, RAGAS scores below their own 0.80 gate, unmeasured
retrieval quality, a 202-second cold start, and one human-plus-AI review
pass rather than an external one. See "Known gaps" below.

The one thing that came out of the load test looking *better* than
documented: all three production monitors fired correctly on the real
incident — the outage check, the faithfulness-drift check, and the
per-region segment check. Regulatory question Q3 is now verified against
an actual incident rather than a simulated one.

## How it works, and why it's built this way

Written for a non-technical reader. Every technical word is explained in
**bold** the first time it appears. The engineering detail is further
down under "SQL architecture" and "Anti-hallucination stack" — this
section is the *reasoning*, not the implementation.

### The journey of one question

Someone asks: *"What is the heat risk for the UK under SSP5-8.5?"*

```
          ┌─────────────────────────────────────────────┐
  QUESTION│                                             │
     │    │  1. Doorman    Is this a climate question?  │
     ▼    │                Any attempt to manipulate?   │
  ┌───────┴──┐                                          │
  │ 2. Permission check   Is this one we're allowed     │
  │                       to answer at all?             │
  └───────┬──┘                                          │
          │                                             │
  ┌───────▼──┐  3. Rulebook   Which approved dataset    │
  │          │                covers this region +      │
  │          │                hazard + scenario?        │
  └───────┬──┘                                          │
          │         ── no match? stop here, say so ──   │
  ┌───────▼──┐  4. Librarian  Find the 5 most relevant  │
  │          │                pages from real documents  │
  └───────┬──┘                                          │
  ┌───────▼──┐  5. Writer     Draft an answer using     │
  │          │                ONLY those pages          │
  └───────┬──┘                                          │
  ┌───────▼──┐  6. Fact-check Strip any data source     │
  │          │                not on the approved list. │
  │          │                Thin evidence? Refuse.    │
  └───────┬──┘                                          │
          │                                             │
  ┌───────▼──┐  7. Logbook    Record everything,        │
  │          │                permanently               │
  └───────┬──┘                                          │
  ANSWER   ▼                                            │
          └─────────────────────────────────────────────┘
```

In this real example: step 3 picked **UKCP18** (the UK Met Office's
official climate projections), step 4 found 5 actual pages from those
reports, and step 7 recorded which pages were used — so the answer can
be checked against its source months later.

### Why each piece exists

The whole design follows from one requirement: **the user must be able
to check the answer against a source.** Each piece below is there
because of a specific way that requirement can fail.

| The piece | Why it exists | What would happen without it |
|---|---|---|
| **The rulebook** (an *approved list* of valid dataset + region + scenario combinations) | The single worst failure for this product is inventing a scientific data source that doesn't exist. An approved list makes that **structurally impossible** rather than merely discouraged | The AI could cite "CMIP7" or "SuperClimate9000" — plausible-sounding, entirely fictional. A planner would have no way to tell |
| **Answering only from retrieved pages** | A sentence the AI produces from memory has no source to check. A sentence drawn from page 64 of a named report does | Answers would be unverifiable by construction — the exact thing a regulator rejects |
| **Four separate safety layers**, not one | Each catches a different failure, and we learned the hard way that a single layer can be silently broken for months. In Round 1 the citation check turned out to be decorative — it could only recognise names that were *already* valid, so it could never catch a fake one | One quiet bug removes all protection, with no outward sign |
| **Hybrid search** — meaning-based *and* exact-keyword, then re-ranked | Meaning-based search misses exact codes like `SSP5-8.5` or `CMIP6`. Keyword search misses paraphrase ("hotter summers" vs "elevated summer temperature"). Climate questions need both | Either missed precise technical terms, or missed relevant pages worded differently |
| **Permission tiers** | Some questions must never be answered automatically *regardless of how good the evidence is* — "should I buy insurance for this property?" is financial advice. That's a legal boundary, not a quality judgement | The system would give regulated advice it isn't licensed to give, however well-sourced |
| **A permanent record of every single query** | A regulator asks "why did you tell them that?" months afterwards. You cannot reconstruct which pages were used after the fact — it has to be captured at the time | The audit question becomes unanswerable, which defeats the point of the product |
| **Refusing instead of guessing** | For this user an unverifiable answer is *worse* than no answer, because it's actionable and wrong at the same time | Confident guesses on planning decisions with real consequences |
| **Separate specialists** (one finds the rulebook path, one searches documents, one does calculations) | When something breaks you can see *which* step broke. A single all-in-one component fails opaquely | Failures become untraceable — you'd know the answer was bad but not why |
| **Monitoring that only raises alarms and never self-corrects** | A system that quietly fixes itself cannot be audited, and nobody learns what went wrong. A named human must decide | Silent self-adjustment — the opposite of an audit trail |
| **An emergency stop that is re-read on every request** | During an incident, "restart the server to apply it" is too slow. This was a real bug: the switch only worked after a restart, which hid the problem | The documented emergency procedure would appear to work while the system kept answering |

### The design principle underneath all of it

**Prefer things that are impossible over things that are forbidden.**

Telling an AI "don't invent dataset names" is an instruction it may or
may not follow. Giving it a fixed list and deleting anything not on that
list is a *structural* guarantee — like a form with a dropdown menu
instead of a free-text box.

That's why the approved-list rulebook is the centre of the design rather
than a carefully worded instruction.

### What the architecture does *not* protect you from

This matters as much as the list above, and we only learned it by
running the system under load on 2026-10-05.

**Good architecture guarantees nothing about running behaviour.** Every
guardrail above worked exactly as designed during that test — and the
system still spent an afternoon telling users the climate evidence was
insufficient when the real cause was a billing limit on the AI service.
Nothing in the design was violated. The outage was correctly detected,
correctly recorded, and correctly alarmed. The failure was in the last
step: the component that writes the user's message couldn't see that
information, so it reached for the nearest honest-sounding explanation —
and that explanation was false.

Two lessons worth carrying:

1. **A structural guarantee only covers what it was designed to cover.**
   "Cannot invent a data source" was true throughout. "Will not make a
   false statement about the evidence" was never designed in, and so it
   wasn't true.
2. **Architecture is checked by reading; behaviour is only checked by
   running.** Five review rounds read this design and approved it. One
   hour of actually serving traffic found nine defects.

The full account, in the same plain language, is in
`docs/what-we-did-in-plain-language.md`.

## Further reading

- **`docs/what-we-did-in-plain-language.md`** — **start here if you
  want the whole story without jargon.** What the problem is, what was
  built, what a load test is and what ours found, every error explained
  simply with why it matters, what LangSmith did and didn't catch, and
  an honest answer to "did this solve the business problem?" Written
  for a non-technical reader.
- **`docs/business-problem-and-alignment.md`** — the business problem
  and the user it's for, where the problem comes from (Williams et al.),
  the ROI model with every input labelled measured-or-assumed, and a
  factual check of what's actually been proven against what the project
  set out to do (includes real per-region data coverage status).
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
  ("deslopify") is and what each of the six rounds on this project
  actually found and fixed, explained for a general audience with no
  unexplained jargon.

## Setup order

Verified working end-to-end on 2026-10-05; the timings below are
measured, not estimated.

1. `docker compose up -d postgres` — starts PostgreSQL + pgvector and
   applies **all** files in `db/migrations/` automatically, but **only
   on first volume init**. An existing volume will not pick up newer
   migrations; drop it or apply them by hand.
2. `python rag/ingest.py` — ~4 minutes for the 4 UKCP18 PDFs, producing
   517 chunks (Land 241, Marine 154, Overview 92, starters guide 30).
   Downloads the embedding model on first run.
   - UKCP18 PDFs must already be in `config.UKCP18_PDF_DIR`.
   - CMIP6/CORDEX/ERA5 NetCDF paths only matter for the analysis agent.
3. `docker-compose up app`, or `python -m uvicorn main:app --port 8000`
   — starts the FastAPI service. **The first query after startup takes
   ~202 seconds** while the embedder and cross-encoder load lazily;
   subsequent queries are 2–20s. Fire one warm-up request before
   pointing real users at it.
4. `streamlit run streamlit_app.py` — starts the frontend.
5. Offline RAGAS evaluation (two phases, two separate venvs — see
   "Real RAGAS evaluation" below for why):
   `./.venv/Scripts/python.exe evaluation/generate_eval_records.py`
   then `./.venv-ragas/Scripts/python.exe evaluation/score_eval_records.py`.
6. `python evaluation/red_team_suite.py` — adversarial guardrail suite.
7. `python evaluation/load_test.py --concurrency 1,2,4,8,16 --requests 16`
   — load test against a running service; see "Known gaps" for results.
8. `python evaluation/online_monitor.py` — runs all three monitoring
   checks once. Nothing schedules this yet; that is a deployment step
   (cron or a cloud scheduler), not something the script can do alone.

Copy `.env.example` to `.env` and fill in `GROQ_API_KEY` and
`LANGSMITH_API_KEY` before starting anything that calls an LLM. Note
that `LITELLM_FALLBACK_MODEL` defaults to an OpenRouter model: without
an OpenRouter key the fallback path raises `AuthenticationError`, so any
primary-model failure becomes a total outage.

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

> Engineering detail. For the plain-language version of what this does
> and *why*, see "How it works, and why it's built this way" above.

Retrieval is a four-stage hybrid pipeline, and the SQL layer is what
makes it both fast and grounded:

1. **SQL pre-filter (always runs first)** — `WHERE dataset = ... AND
   scenario = ... AND region IN (...)`, driven by the KG agent's
   traversal result, applied before any embedding math happens.

   > **Measured reality (2026-10-05), which is not what this section
   > used to claim.** Against the actual ingested corpus the pre-filter
   > does not narrow — it gates. `ingest_directory()` tags every chunk
   > `dataset='UKCP18'` and leaves `scenario` and `region` `NULL`, and
   > those two clauses tolerate `NULL`, so they match everything:
   >
   > | Query resolves to | Rows surviving, of 517 |
   > |---|---|
   > | UKCP18 + SSP5-8.5 + UK/Global | **517** (narrows nothing) |
   > | CMIP6 + SSP5-8.5 + Mumbai | **0** (excludes everything) |
   > | ERA5 + SSP5-8.5 + Kerala | **0** (excludes everything) |
   >
   > This section previously said it "narrows ~10,000 chunks to ~200"
   > for "a ~50x smaller search space." Those were design aspirations
   > stated as measurements; the corpus is 517 chunks and the filter is
   > all-or-nothing on the dataset tag. It is also the real reason
   > Kerala and Mumbai questions retrieve nothing — an honest refusal,
   > but by a different mechanism than described. See `MAINTENANCE.md`
   > Round 6, finding 7.
2. **pgvector semantic search** — cosine similarity over the SQL-
   filtered candidates only.
3. **BM25 keyword search** — exact-match strength on terms like
   `CMIP6`, `SSP5-8.5`, `Kerala`, fused with vector ranks via
   reciprocal rank fusion (RRF).
4. **Cross-encoder reranking** — `cross-encoder/ms-marco-MiniLM-L-6-v2`
   reranks the fused top 20 down to the final top 5, with full source
   metadata attached.

The intended design: the knowledge graph constrains **what** datasets
are valid; SQL constrains **which** chunks are searched; vector search
finds **relevant** content; the reranker selects the **best** 5 chunks.
The first and last stages are verified working — a UK heat question
traverses five KG nodes and returns 5 real UKCP18 pages.

Two honest corrections to what this section used to assert:

- **"A ~50x smaller search space per query"** — not true of the current
  corpus; see the measured table above. The claim will become true once
  chunks carry region and scenario tags and the corpus is large enough
  for narrowing to mean anything.
- **"Zero hallucinated dataset citations"** — still true in the sense
  that matters (nothing invented has ever reached a user), but the
  mechanism currently over-fires: it strips valid emissions-scenario
  labels, including `SSP5-8.5`, out of answers. See the next section
  and `MAINTENANCE.md` Round 6, finding 1.

## Anti-hallucination stack

> Engineering detail. The plain-language reasoning for why there are
> four independent layers rather than one is in "How it works, and why
> it's built this way" above.

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
| UK (the proof case) | ✅ 4 UKCP18 PDFs, 517 chunks | RAG-grounded answers verified live. The only region that retrieved any context in the last eval run — 2 of 10 test questions (London, UK), both UKCP18; the other 8 correctly refused |
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
fixed across six maintenance rounds — this list is what's still open:

- ~~**A rate-limited LLM outage is reported as "insufficient
  grounding"**~~ — **fixed 2026-10-05, verified under load.**
  `apply_output_filter()` now takes `llm_unavailable` and checks it
  before the groundedness threshold, returning a message that says the
  model service failed and explicitly states it is *not* a judgement
  about the climate evidence. Same 16-request workload at concurrency
  16: answers claiming "insufficient grounding" went from **10 to 0**,
  and the 9 real outages are now named. Round 6, finding 2.
- ~~**The output filter destroys valid scenario labels by
  substring**~~ — **fixed 2026-10-05.** Two bugs, two fixes: removal now
  uses `re.sub` with `\b` word boundaries instead of `str.replace` (so a
  flagged short token can't rewrite longer ones), and the vocabulary now
  includes bare scenario-family acronyms — `SSP` derived automatically
  from `schema.json`, plus `RCP` — with a stem check that also exempts
  unlisted family members like `RCP8.5` and `RCP2.6`. The live answer
  that returned `[UNVERIFIED DATASET REMOVED]5-8.5` now returns
  `SSP5-8.5`, `RCP8.5` and `RCP2.6` intact. This does **not** assert any
  RCP↔SSP equivalence — that remains an owner decision. Round 6,
  finding 1.
- ~~**`/query` never returns `llm_unavailable`**~~ — **fixed
  2026-10-05.** The field is now in the response, so a caller can tell
  an outage from a refusal. Round 6, finding 3.
- **LangSmith recorded the entire outage as 100% successful.** Tracing
  is wired up and genuinely receiving traces (APAC endpoint, project
  `climate-risk-agent`), but queried after the incident it held 100
  spans, **every one `status="success"` with no error set**, logged
  during the window in which 70 of 91 queries failed. Cause: every span
  is `run_type="chain"` — there are **no LLM spans at all**, because
  `call_llm()` carries no `@traceable` and litellm's LangSmith callbacks
  aren't configured, so the 89 rate-limit errors have no span to appear
  in. Only 4 functions are traced, all agent entry points; retrieval
  and all four guardrails are untraced. The three places the real
  defects live are the three with no instrumentation. Round 6,
  finding 9.
- **The analysis agent fails on every UK query, and the failure leaks
  into the answer.** UKCP18 is a PDF corpus with no NetCDF, so the
  agent always errors — and `_combine_results()` passes the failed
  result into the prompt, where the model cites it as a reason the
  climate evidence is insufficient. Round 6, finding 4.
- **Cold start is 202 seconds.** The embedder and reranker load lazily
  on first request and the `lifespan` hook doesn't warm them, so the
  first user after every deploy waits ~3.5 minutes. Warm requests are
  2–20s. Round 6, finding 6.
- ~~**`python evaluation/online_monitor.py` fails**~~ — **fixed
  2026-10-05.** The script now bootstraps the project root onto
  `sys.path` the way its four sibling scripts already did, so the
  command this README documents actually works. Verified: all three
  checks run. Round 6, finding 5.
- **No API authentication** — anyone who can reach the FastAPI endpoint
  can use it. There is no auth of any kind in `main.py`.
- **Answer quality is below its own gate** — real RAGAS scores are
  0.778 faithfulness / 0.473 relevancy against a 0.80 target (see "Real
  RAGAS evaluation" above). This needs prompt/retrieval tuning and
  probably an SSP↔RCP scenario mapping, not a bug fix.
- **Retrieval quality is unmeasured** — no precision@k, recall@k, or
  MRR. For a system whose value rests entirely on retrieving the right
  page, this is the largest measurement hole.
- **False-refusal rate is unmeasured** — correct refusals are proven
  (8 of 10 eval questions, all correctly). How often it refuses
  something it *could* have answered is unknown, and both the RCP8.5
  finding and the hedged UK answers suggest it leans too cautious.
- **~~Never load-tested~~ — done 2026-10-05, and it found most of the
  defects above.** `evaluation/load_test.py` ramps an identical
  16-request workload at in-flight limits of 1/2/4/8/16 and reports
  P50/P95/P99 latency, throughput, and errors classified by failure
  mode. Measured, cache disabled:

  | Max in flight | Wall | Throughput | p50 | p95 |
  |---|---|---|---|---|
  | 1 | 63.0s | 0.25 req/s | 4.27s | 8.39s |
  | 2 | 39.7s | 0.40 req/s | 5.12s | 10.10s |
  | 4 | 32.7s | 0.49 req/s | 7.83s | 20.68s |
  | 8 | 27.3s | 0.59 req/s | 7.40s | 23.72s |
  | 16 | 23.1s | 0.69 req/s | 19.43s | 23.06s |

  **Throughput scales badly** — 16x the concurrency buys 2.7x the
  throughput, while p50 latency degrades 4.5x. **The breaking point is
  Groq's free-tier input-token limit (ITPM 7,000)**, reached from about
  two concurrent requests upward.

  The important result is not in the table. On the *identical* workload,
  substantive answers fell from 4 at concurrency 1 to **0 at
  concurrency 16**, while "insufficient grounding" responses rose from 6
  to 10 — every one of them HTTP 200. Quality collapsed under load and
  no status code moved. That is the finding that only a load test which
  inspects answers, not just response codes, can produce.
- **Still not load-tested: anything above 16 concurrent, or on a paid
  tier.** Nothing failed outright at 16, so the ceiling of the
  non-LLM parts of the stack (the 10-connection DB pool, the analysis
  subprocess) is still unmeasured — the rate limit masks them. The
  next run should stub the LLM layer.
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
