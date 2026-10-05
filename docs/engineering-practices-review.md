# Does This Project Follow a Real AI Engineer Learning Path?

This document checks this project against two pieces of external
advice, step by step, honestly: an 11-step guide describing what a
complete, hire-ready AI-engineering project looks like, and a separate
framework for what to measure once it's running. Both are from Lan Chu
(the same source named in `MAINTENANCE.md` Round 4). What matters below
is whether the advice holds up against this codebase, not who gave it —
but it's named rather than anonymised so a reader can go and check the
original.

Every jargon term is explained the first time it appears, in **bold**.

---

## Part 1 — The 11-step build path

| # | Step | Status | What's actually true |
|---|---|---|---|
| 1 | Understand what happens inside an LLM API call (**prefill** = the model reading your prompt before it starts answering; **decoding** = generating the answer one piece at a time; **tokens** = the small chunks of text a model reads/writes in, roughly 3/4 of a word each) | 🟡 Practical, not theoretical | We never studied inference internals directly, but we hit the *practical* consequence hard: Groq's free tier caps how many tokens a model can generate per minute, and a chain-of-thought model can silently spend its entire budget "thinking" before writing an answer, leaving nothing for the actual response. We debugged this for real and fixed it (see `MAINTENANCE.md`), which is arguably a better education in token mechanics than reading about prefill/decoding in the abstract. |
| 2 | Build a backend around the model with a web framework, thinking about conversation history, where state lives, and authentication | 🟡 Mostly done | A FastAPI backend exists with `/query`, `/health`, `/audit/{id}` endpoints. State (the running record of one question's progress through the system) lives in a structured Python object per request. **Missing:** there is no multi-turn conversation memory — each question is independent, with no "remember what I asked earlier" — and there is no authentication on the API at all (anyone who can reach it can use it). Both are real, undone gaps, not oversights hidden in the code. |
| 3 | Build a frontend, connect it to the backend, watch data move end to end | ✅ Done, verified live | A Streamlit page sends a question to the backend and displays the answer, the reasoning path, confidence score, and cost. This was tested with a real question and a real screenshot, not just written and assumed to work. |
| 4 | Add external knowledge: a **RAG** (**R**etrieval-**A**ugmented **G**eneration — instead of the model answering from memory, you hand it real, retrieved documents to answer from) pipeline with chunking, embeddings, a vector database, and search | ✅ Done, verified live | Real PDF documents are split into pieces (**chunking**), turned into number-vectors (**embeddings**) that capture meaning, stored in a database built for searching by meaning (**pgvector**), and retrieved with a 4-stage search. This was tested with real questions returning real document excerpts. |
| 5 | Add evaluations and observability: a reference dataset, chosen metrics, and a platform to see full traces (prompt, retrieved chunks, output, tool calls, latency, cost) | 🟡 Evals partially done; **observability downgraded on measurement** | A reference dataset of 10 test questions exists. **RAGAS** genuinely runs and produced real numbers: 0.778 faithfulness, 0.473 answer relevancy, both below the 0.80 target; context precision needs real reference answers per question and currently returns a meaningless 0.0. **LangSmith** (a platform that records every step an AI system takes) is wired in and genuinely receiving traces — but queried after the 2026-10-05 incident it held 100 spans, **all marked successful, none with an error**, logged while 70 of 91 queries were failing outright. Every span is a coordination step; there are **no LLM spans at all**, so the rate-limit failures have nowhere to appear. The prompt, the retrieved chunks, the tool calls and the token/cost figures this step asks for are mostly *not* in the traces — cost lives in the audit table instead. Round 6, finding 9. |
| 6 | Add agentic components: let the model call tools, external APIs, or a database, in simple workflows | ✅ Done, verified live | Three specialised pieces (called **agents** — each one is a focused worker with one job) exist: one traverses a strict rulebook of valid climate datasets, one searches real documents, one writes and runs real Python code against real climate data files. All three were tested with real questions and produced real, correct outputs. |
| 7 | Make it reliable: strict output validation, retries and timeouts, handling empty results, async so one slow request doesn't block others | 🟡 Mostly done, with one bug found and fixed | Strict output templates (**Pydantic** validation) are used throughout. Retries and a backup model exist for when the primary one fails. Empty search results are handled without crashing. Everything runs **async** (a way of writing code so that while one task is waiting — e.g. for a slow network response — the program can work on something else instead of just sitting idle). **The bug:** the backup-model logic was found to be broken in a way that could crash a request entirely instead of failing gracefully; this has been fixed and is now backed by a test. |
| 8 | Test the entire system: unit tests, integration tests, end-to-end tests | 🟡 Downgraded after measurement | **52** unit tests pass in **13–19 seconds** (re-run and timed 2026-10-05; the "45 tests" figure here was stale). 4 integration tests also pass — but in **3m34s to 9m23s** (measured twice; runtime is dominated by LLM rate-limit backoff), and one of those runs completed during a window in which 70 of 91 queries were in total LLM outage. Three of the four only exercise short-circuit paths that never call an LLM; the fourth skips itself conditionally and then asserts only that two keys exist in the audit record, nothing about the answer. So the suite cannot distinguish a healthy system from one failing three quarters of its queries. Plus a 10-question adversarial suite probing the safety rules. See `MAINTENANCE.md` Round 6, finding 8. |
| 9 | Deploy: put it in a container, orchestrate multiple services, push to a registry, set up automatic testing on every code change | 🟡 Configured, partially exercised | Docker Compose is now actually used to run PostgreSQL (verified live, used throughout the real-data debugging in this project). The app container itself has still never been started through Docker — every real test ran the FastAPI/Streamlit services by hand instead. There is no container **registry** (a place to store and share a packaged, ready-to-run version of the app) in use. The project is now in version control and pushed to GitHub, with `.github/workflows/ci.yml` configured to run on every push — but it hasn't produced a real passing run yet, since the repository's `GROQ_API_KEY` secret still needs to be configured, and its RAGAS-scoring job is expected to fail on real quality thresholds (0.778/0.473 vs. 0.80) even once it does run. |
| 10 | Test under real load: send many requests at once, watch things break, fix them one by one | ✅ **Done 2026-10-05** — and it was the highest-value step in this entire list | `evaluation/load_test.py` ramped an identical 16-request workload at in-flight limits of 1/2/4/8/16. Throughput scaled badly (16x concurrency → 2.7x throughput, p50 latency 4.27s → 19.43s) and the breaking point was found: Groq's free-tier **input**-token limit, ITPM 7,000, reached from roughly two concurrent requests. But the finding that mattered wasn't a number — on the identical workload, substantive answers fell from 4 at concurrency 1 to **0 at concurrency 16**, with zero HTTP errors throughout, because rate-limited outages were being presented to users as honest "insufficient grounding" refusals. Five further defects fell out of the same run. Full account: `MAINTENANCE.md` Round 6. |
| 11 | Optimize cost and latency: caching, routing simple requests to smaller/cheaper models, measure-then-optimize-then-retest | 🟡 Measured at last, not yet optimized | There's a router that sends simple, non-climate-retrieval questions straight to the model without running the full pipeline — a real form of "route simpler requests differently," and the load test confirmed it works: short-circuited requests returned in as little as 0.07s against a 4–20s full-pipeline answer. Response caching is now **confirmed working** (a repeated question returned in 7s against a 202s cold start) — in fact the first load-test run had to be discarded because it was measuring cache hits. **The measure step is now done** (p50/p95 across a concurrency ramp, throughput, cold start, breaking point — see below). **What's still missing is the optimize-and-re-measure half:** nothing has been changed in response to those numbers, and the two obvious candidates are plain — warm the models at startup to kill the 202s cold start, and cut the input-token footprint per query, since the binding limit turned out to be input tokens rather than output. |

**Quick count (revised 2026-10-05):** of 11 steps, roughly **6 are
solidly done** (load testing joined them), **4 are partially done with a
specific, named gap**, and **1 — step 8, testing — was downgraded**,
because re-running the suite showed the integration tests pass whether
the system is healthy or failing 77% of its queries. None were skipped
silently.

Worth noting what moving step 10 from ❌ to ✅ actually did: it did not
tick a box, it produced six new defects and invalidated three claims
elsewhere in these docs. The weakest-looking step on the list was the
one carrying the most information.

---

## The load test — specified, then run (step 10)

This section was written as a recipe for work not yet done. The work has
since been done, on 2026-10-05, and the results are folded in below. The
recipe is kept because it is still the right recipe, and because the
difference between what it predicted and what happened is the most
useful thing on this page.

> **Headline result.** The prediction below — that the free-tier rate
> limit would break first and would mask everything else — was correct.
> What the recipe did *not* anticipate is that the rate limit would not
> surface as an error at all. It surfaced as **polite, plausible
> refusals at HTTP 200**: 70 of 91 logged queries were in total LLM
> outage, and every one told the user the *evidence* was insufficient.
> A load test measuring only latency, throughput and status codes would
> have passed this system with zero failures at every concurrency level.
> That is exactly what the first version of the report said before the
> audit log was checked.

**What a load test means here.** Fire many questions at the system at
once and measure three things:

| What to measure | Definition in plain terms |
|---|---|
| **Latency percentiles** — P50, P95, P99 | The time by which half, 95%, and 99% of requests have finished. An average hides the tail; P99 is where real users notice |
| **Throughput** | Requests completed per second, and how that number changes as concurrency rises |
| **Errors, broken down by type** | Not a single error count — a count per failure mode |

**The goal is to find where it breaks, not to prove it's fast.** A run
where nothing fails has told you nothing except that you didn't push
hard enough. Ramp concurrency until something gives, then record what
gave first.

**Why errors must be split by type in this system specifically.** There
are at least four distinct failure modes behind this API, and they need
completely different fixes:

1. **Groq rate-limit rejections** — the free tier's requests- and
   tokens-per-minute caps. Already hit accidentally. Expected to be the
   *first* thing that breaks, which makes it the least interesting
   finding and the one most likely to mask the others.
2. **Database connection pool exhaustion** — `config.DB_POOL_MAX_SIZE`
   defaults to 10. Every query opens a session for retrieval, and the
   audit write opens another.
3. **Analysis-subprocess timeouts** — each analysis run spawns a fresh
   Python subprocess that imports xarray/dask/matplotlib, which
   `config.py` notes can take 15–36 seconds *before* any computation.
   `ANALYSIS_TIMEOUT` is 90 seconds. Several of those in parallel
   compete for the same CPU, so the timeout becomes reachable under
   concurrency in a way it isn't for a single request.
4. **Both-models-failed (`llm_unavailable`)** — the primary and fallback
   LLM calls both failing. The system already distinguishes this from a
   legitimate refusal and alerts on a single occurrence
   (`evaluation/online_monitor.py`), which is exactly the signal a load
   test should be watching.

An aggregate "7% error rate" is useless across those four. "6% rate
limit, 1% pool exhaustion, 0 timeouts" tells you to get a paid tier and
stop worrying about the pool.

### What the four predicted failure modes actually did

| Predicted mode | What happened on the real run |
|---|---|
| 1. Groq rate-limit rejections | ✅ **Confirmed, and it dominated** — 89 `RateLimitError`s, all naming input tokens per minute (ITPM) limit 7,000. Reached from ~2 concurrent requests. Each query stuffs 5 retrieved UKCP18 chunks into the prompt, so input tokens, not output, are the binding constraint — a detail the prediction missed |
| 2. DB connection pool exhaustion | ➖ **Never reached.** The rate limit throttles the system below the point where 10 connections matter. Still unmeasured, exactly as predicted |
| 3. Analysis-subprocess timeouts | ➖ **Never reached, for an unexpected reason** — the analysis agent fails instantly on every UK query because UKCP18 has no NetCDF files, so it never runs long enough to time out. A real defect found by accident (Round 6, finding 4) |
| 4. Both-models-failed (`llm_unavailable`) | ✅ **Confirmed, 70 times — and invisible.** The fallback is an OpenRouter model with no key, so every rate-limited primary call became a total outage (178 `AuthenticationError`s). Crucially, `/query` does not return `llm_unavailable`, so the load test could not see any of it. The count came from the audit-log table afterwards |

**The lesson for anyone else writing one of these:** classify errors by
type *and* make sure the API actually exposes the state you want to
classify by. This system had the right flag, set correctly, written
faithfully to the database — and the HTTP response left it out, which
made the load test blind to the only failure that was happening.

### Measured results

Identical 16-request workload at each level; LLM response cache
disabled; in-flight limit bounded by a semaphore so only concurrency
varies.

| Max in flight | Wall | Throughput | p50 | p95 | HTTP failures | Substantive answers |
|---|---|---|---|---|---|---|
| 1 | 63.0s | 0.25 req/s | 4.27s | 8.39s | 0 | 4 |
| 2 | 39.7s | 0.40 req/s | 5.12s | 10.10s | 0 | 1 |
| 4 | 32.7s | 0.49 req/s | 7.83s | 20.68s | 0 | 1 |
| 8 | 27.3s | 0.59 req/s | 7.40s | 23.72s | 0 | 1 |
| 16 | 23.1s | 0.69 req/s | 19.43s | 23.06s | 0 | **0** |

Three readings, in increasing order of importance:

1. **Throughput scales badly.** 16x the concurrency returns 2.7x the
   throughput, and p50 latency degrades 4.5x to get it. The system is
   contended, not parallel.
2. **Cold start dominates everything.** The very first request after a
   restart took **202 seconds** — the embedder and cross-encoder load
   lazily and the startup hook doesn't warm them. That single number is
   larger than every other latency measurement combined, and it is what
   the first user after each deploy experiences.
3. **Answer quality collapsed while the error count stayed at zero.**
   Substantive answers: 4 → 0. This is the entire argument for
   inspecting answers in a load test, and it is why this script
   classifies response bodies rather than counting status codes.

An earlier run with the cache enabled produced flattering numbers
(p50 2.59s at concurrency 1) and is not reported above, because repeated
identical questions were being served from the LiteLLM cache. If you
re-run this, disable the cache or you will measure the cache.

**Quality failures count as findings too.** The original advice is
explicit that what surfaces under load isn't only infrastructure errors
— retrieval gets worse and tool calls go wrong. That applies here: the
reranker and the embedding model are loaded in-process and compete for
CPU with every concurrent request and with any analysis subprocess, so
degraded retrieval under load is a realistic outcome, not a
hypothetical. A load test that records only HTTP status codes would miss
it entirely. Capture the answers, not just the response codes.

**One caveat on sequencing.** Because failure mode 1 is near-certain to
dominate on the free tier, a load test run today mostly measures Groq's
rate limiter rather than this system. To learn anything about modes 2–4,
either run against a paid tier, or stub the LLM layer and load-test the
retrieval and audit paths on their own. Both are legitimate; what isn't
legitimate is running it once, hitting the rate limit, and recording
"load tested."

### Which of the framework's scalability metrics actually apply here

The metrics framework in Part 2 below names six scalability metrics.
Four apply to this system, two do not — and the reason two don't is
architectural, not an oversight:

| Metric | Applies? | Why |
|---|---|---|
| **RPS** (requests per second) | ✅ Yes | This is the throughput number the load test should produce |
| **Cost per request** | ✅ Yes | Already tracked per query (`litellm_cost_usd`), currently $0.00 on the free tier |
| **Cache hit rate** | ✅ Yes, and untested | `config.LITELLM_CACHE_ENABLED` defaults to true but has never been verified end to end. A load test that repeats questions is the natural place to measure it |
| **Latency percentiles** (P50/P95/P99) | ✅ Yes | Not in the original framework's list, but the right latency metric for a non-streaming API like this one |
| **TTFT** (time to first token) | ❌ Not meaningful | This API does not stream. `main.py` returns one JSON object after the entire pipeline completes, and `call_llm` uses a non-streaming completion call. So TTFT is identical to total latency — there is no "first token" a user sees early. It would become a real metric only if the answer were streamed, which is a product decision, not a measurement one |
| **ITL** (inter-token latency) | ❌ Not applicable | Same reason — no token-by-token delivery exists to measure the gaps in |

**And one metric the framework lists that would mislead here:** TPS
(tokens per second). It is measurable per LLM call, but it is not this
system's bottleneck. A single query spends most of its wall-clock time
in retrieval, cross-encoder reranking, and — when the analysis agent
runs — a subprocess that spends 15–36 seconds importing libraries before
it computes anything. Optimising tokens per second would be optimising a
minority of the latency. Measure where the time actually goes first; the
framework's own closing advice is "measure first, then optimize," and
this is a case where picking the wrong metric would send the optimisation
work to the wrong place.

---

## Part 2 — The performance-metrics framework

The second piece of advice you found groups what to measure into four
buckets. Here's the honest status of each metric this project *could*
track, and whether it actually does.

### 1. Quality — does it do the task well?

| Metric | Plain-language meaning | Tracked here? |
|---|---|---|
| Precision@k / Recall@k | Of the documents retrieved, how many are actually relevant (**precision**), and of all the relevant documents that exist, how many did we find (**recall**) — both measured on the top *k* results | ❌ Not measured |
| MAP@k | A single score summarising whether relevant results consistently appear near the top, averaged across many questions | ❌ Not measured |
| MRR@k | How early the *first* relevant result shows up, on average | ❌ Not measured |
| Answer relevance & faithfulness | Does the answer actually address the question, and is every claim in it backed by the retrieved evidence | 🟡 Two different numbers, and the distinction matters. **Offline:** genuinely measured by an AI judge — 0.778 faithfulness, 0.473 relevancy, both below the 0.80 gate. **Online, per query:** a simplified stand-in (does grounded evidence exist?) used to gate answers, honestly flagged as unmeasured on every audit record via `faithfulness_measured: false` |
| LLM-judge alignment (**Cohen's Kappa**, **Spearman**, **Kendall's Tau** — three different statistical ways of checking whether an AI's judgement of quality agrees with a human's judgement) | Do automated quality scores actually agree with what a human would say | ❌ Not measured |
| Tool-call error rate / steps per task | How often does a step in the pipeline fail, and how many steps does a typical question take | ❌ Not tracked as a standing metric, though individual failures are logged |
| Eval suite run across changes | Re-run the same test questions every time you change a prompt or model, to see if scores improved or got worse | 🟡 The test suites exist and can be re-run, but no history of "score before vs. after a specific change" has been kept |

### 2. Scalability — can you run it at scale?

| Metric | Plain-language meaning | Tracked here? |
|---|---|---|
| TTFT (**Time To First Token**) | How long you wait before the answer starts appearing at all | ➖ Not applicable, not merely unmeasured — this API doesn't stream, so TTFT equals total latency. See "Which of the framework's scalability metrics actually apply here" above |
| ITL (**Inter-Token Latency**) | How long between each small piece of the answer as it's being generated | ➖ Not applicable — same reason; there is no token-by-token delivery to measure |
| TPS / RPS (**Tokens Per Second** / **Requests Per Second**) | How much the system can produce or handle per second | ✅ **RPS measured** — 0.25 req/s at 1 in flight rising to 0.69 at 16 (see step 10). TPS remains measurable but misleading here, since token generation isn't the bottleneck |
| Latency percentiles (P50/P95/P99) | The time by which half, 95%, and 99% of requests finish | ✅ **Measured** — p50 4.27s → 19.43s and p95 8.39s → 23.06s across the concurrency ramp, plus a **202s cold start**. This also corrects the old "~35–90 seconds" figure in these docs, which was an informal observation and matched neither the warm nor the cold reality |
| Cache hit rate | What fraction of requests are answered from a saved previous result instead of doing the work again | 🟡 Still not measured as a rate, but the cache is now **confirmed working** — an identical repeated question returned in 7s against 202s cold, and the first load-test run had to be discarded and re-run with the cache disabled because it was measuring cache hits rather than the system |
| Cost per request | How much each question costs in API fees | ✅ Tracked — every request logs its actual cost, and because the free tier was used throughout, the real logged cost has been $0.00 |

### 3. Safety — does it stay within the boundaries you set?

| Metric | Plain-language meaning | Tracked here? |
|---|---|---|
| Policy violation rate | How often the system breaks its own safety rules | 🟡 Tested via a fixed set of 10 adversarial questions (currently 0 violations), but not tracked as an ongoing *rate* over real traffic. The load test adds supporting evidence: across 80+ requests including injection and Tier-1 financial-advice prompts, the guardrails held every time — tier-1 blocks, injection blocks, coverage-gap refusals and clarification requests all fired correctly under concurrency |
| Refusal rate / false-refusal rate | How often the system correctly says "I can't answer that," versus how often it *wrongly* refuses a question it actually could have answered | 🟡 Correct refusals are well established — 8 of the 10 evaluation questions refused, every one of them correctly. **False**-refusal rate still unmeasured, but no longer a neutral unknown: see below. |

The framework makes an important point here worth repeating in plain
terms: **a system that refuses every question is perfectly "safe" and
also completely useless.**

**This is no longer an unknown. It was measured on 2026-10-05, and the
answer is bad.**

Under load, on an identical 16-request workload, substantive answers
fell from 4 (at 1 request in flight) to **0** (at 16), while
"insufficient grounding" responses rose from 6 to 10. The audit log
explains why: **70 of 91 queries were in total LLM outage** and all 70
were reported to the user as insufficient evidence.

So the false-refusal rate under concurrency approaches 100% of
answerable questions, and essentially none of those refusals are honest
— they are infrastructure failures wearing a refusal's clothes. Two
further contributors, both confirmed:

1. **Answers that do get through are over-hedged.** Both scoring UK
   answers retrieve the right pages, then spend their length explaining
   why they can't answer precisely. Grounded and true — and not what was
   asked. That's what the 0.473 answer relevancy measures.
2. **The citation guardrail over-fires destructively.** The bare string
   `SSP` is stripped as an unverified dataset citation, and because the
   removal is a substring replace it takes `SSP5-8.5` and `SSPs` with
   it — so a question *about* `SSP5-8.5` returns an answer discussing
   `[UNVERIFIED DATASET REMOVED]5-8.5`. Reproduced live and in
   isolation; `MAINTENANCE.md` Round 6, finding 1.

The framework's warning — that a system refusing everything is perfectly
safe and completely useless — turned out to describe this system under
load, precisely. And the thing that makes it dangerous rather than
merely useless is that the refusals are *articulate*: they cite the
evidence, name the scenario mismatch, and read exactly like careful
scientific caution.

### 4. Operational reliability

| Metric | Plain-language meaning | Tracked here? |
|---|---|---|
| Error rate on failed calls | How often a call to the AI model, a tool, or the search step fails outright | ✅ **Measured, and the number is bad** — 70 of 91 logged queries (77%) were in total LLM outage during the load test, queryable from `audit_log.llm_unavailable`. The tracking added in Round 4 works; the monitor fired correctly on all of it. What's still missing is a standing dashboard rather than a monitor you have to run by hand, and an API that exposes the flag to callers (Round 6, finding 3) |

---

## Bottom line

**Does this project follow the 11-step path?** Substantially yes for
the first eight steps (understanding the model, backend, frontend, RAG,
partial evals, agents, reliability, testing) — each has been built and,
where claimed "done," verified with a real question and real data. Step
10 is now done too, and doing it changed the assessment of several
earlier steps rather than just adding a tick: step 7 (reliability) and
step 8 (testing) both look weaker than they did, because the system
degrades silently under load and the test suite cannot detect it.

The honest current ranking of the weak steps: **step 9 (deployment)** —
the app container has still never been started through Docker, and CI
has never completed a real run; **step 11 (cost/latency)** — now at
least measured, but no measure-optimize-retest cycle has been run
against the numbers; and **step 8 (testing)** — the suite runs green
through a 77% failure rate.

**Does it track the recommended metrics?** Materially better than when
this was written. Of roughly 16 named metrics across the four
categories, **six** are now tracked as real numbers: cost per request,
generation quality (RAGAS faithfulness/relevancy), **RPS**, **latency
percentiles**, **LLM error rate**, and **false-refusal behaviour under
load** — the last four all produced by the load test. **Two don't apply
to this architecture at all** — TTFT and ITL, because nothing streams;
counting them as gaps would pad the list with work that shouldn't be
done.

What remains genuinely untracked: **retrieval quality** (precision@k,
recall@k, MRR), **LLM-judge agreement** (Cohen's Kappa against a human
judge), and **cache hit rate** as a standing rate.

This isn't a reason to be discouraged — it's a straightforward,
prioritised to-do list. Two of the gaps this section used to name are
now closed: getting the real evaluation library working (the RAGAS fix),
and operational reliability — error-rate tracking on failed LLM calls
now exists via the `llm_unavailable` flag and the outage check in
`evaluation/online_monitor.py` (`MAINTENANCE.md` Round 4), which is
exactly the gap that let Groq silently renaming a model go unnoticed in
Round 2.

**The next highest-value work is no longer a measurement gap — it's two
defects.** The load test reordered this list:

1. **Stop reporting outages as refusals** (Round 6, finding 2). A system
   whose entire value proposition is traceable answers must not tell a
   planner the climate evidence was thin when the truth is that the
   model provider rate-limited it. `apply_output_filter()` needs to know
   about `llm_unavailable` and say something different, and `/query`
   needs to expose the flag.
2. **Fix the substring citation strip** (finding 1). A question about
   `SSP5-8.5` currently returns an answer about
   `[UNVERIFIED DATASET REMOVED]5-8.5`.

**Then** retrieval quality measurement (precision@k, recall@k, MRR),
which remains the biggest genuine measurement hole. The reasoning is
specific to this project: the business case is "answers you can check
against a source," the only region with real ingested data is the UK,
and answers retrieve pages and then fail to use them. Every one of those
is a statement about retrieval, and none of it is measured. Generation
metrics tell you the answer was weak; retrieval metrics tell you whether
the right page was even on the table. We still can't distinguish
"retrieved the wrong chunks" from "retrieved the right chunks and wrote
a poor answer from them," and those need opposite fixes.

A note on sequencing, learned the hard way this round: the two defects
come first not because they're easier but because **they corrupt the
measurements.** Any retrieval-quality number computed while 77% of
queries silently return a canned refusal would measure the rate limit,
not the retrieval.
