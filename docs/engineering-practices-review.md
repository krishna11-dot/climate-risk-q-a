# Does This Project Follow a Real AI Engineer Learning Path?

You found an 11-step guide describing what a complete, hire-ready
AI-engineering project looks like, plus a separate framework for what
to measure once it's running. This document checks this project against
both, step by step, honestly. Sources are described generically
(no names) since what matters is whether the *advice* holds up, not who
said it.

Every jargon term is explained the first time it appears, in **bold**.

---

## Part 1 — The 11-step build path

| # | Step | Status | What's actually true |
|---|---|---|---|
| 1 | Understand what happens inside an LLM API call (**prefill** = the model reading your prompt before it starts answering; **decoding** = generating the answer one piece at a time; **tokens** = the small chunks of text a model reads/writes in, roughly 3/4 of a word each) | 🟡 Practical, not theoretical | We never studied inference internals directly, but we hit the *practical* consequence hard: Groq's free tier caps how many tokens a model can generate per minute, and a chain-of-thought model can silently spend its entire budget "thinking" before writing an answer, leaving nothing for the actual response. We debugged this for real and fixed it (see `MAINTENANCE.md`), which is arguably a better education in token mechanics than reading about prefill/decoding in the abstract. |
| 2 | Build a backend around the model with a web framework, thinking about conversation history, where state lives, and authentication | 🟡 Mostly done | A FastAPI backend exists with `/query`, `/health`, `/audit/{id}` endpoints. State (the running record of one question's progress through the system) lives in a structured Python object per request. **Missing:** there is no multi-turn conversation memory — each question is independent, with no "remember what I asked earlier" — and there is no authentication on the API at all (anyone who can reach it can use it). Both are real, undone gaps, not oversights hidden in the code. |
| 3 | Build a frontend, connect it to the backend, watch data move end to end | ✅ Done, verified live | A Streamlit page sends a question to the backend and displays the answer, the reasoning path, confidence score, and cost. This was tested with a real question and a real screenshot, not just written and assumed to work. |
| 4 | Add external knowledge: a **RAG** (**R**etrieval-**A**ugmented **G**eneration — instead of the model answering from memory, you hand it real, retrieved documents to answer from) pipeline with chunking, embeddings, a vector database, and search | ✅ Done, verified live | Real PDF documents are split into pieces (**chunking**), turned into number-vectors (**embeddings**) that capture meaning, stored in a database built for searching by meaning (**pgvector**), and retrieved with a 4-stage search. This was tested with real questions returning real document excerpts. |
| 5 | Add evaluations and observability: a reference dataset, chosen metrics, and a platform to see full traces (prompt, retrieved chunks, output, tool calls, latency, cost) | 🟡 Partially done | A reference dataset of 10 test questions exists. An observability tool (**LangSmith** — a platform that records every step an AI system takes, for later inspection) is wired in. The scoring library (**RAGAS**) now genuinely runs (it didn't when this row was first written) and produced real numbers: 0.778 faithfulness, 0.473 answer relevancy, both below the 0.80 target. **What's still missing:** the third metric (context precision) needs real reference answers per question, which the test dataset doesn't have yet — it currently returns a meaningless 0.0. See `docs/business-problem-and-alignment.md` for the full honest breakdown. |
| 6 | Add agentic components: let the model call tools, external APIs, or a database, in simple workflows | ✅ Done, verified live | Three specialised pieces (called **agents** — each one is a focused worker with one job) exist: one traverses a strict rulebook of valid climate datasets, one searches real documents, one writes and runs real Python code against real climate data files. All three were tested with real questions and produced real, correct outputs. |
| 7 | Make it reliable: strict output validation, retries and timeouts, handling empty results, async so one slow request doesn't block others | 🟡 Mostly done, with one bug found and fixed | Strict output templates (**Pydantic** validation) are used throughout. Retries and a backup model exist for when the primary one fails. Empty search results are handled without crashing. Everything runs **async** (a way of writing code so that while one task is waiting — e.g. for a slow network response — the program can work on something else instead of just sitting idle). **The bug:** the backup-model logic was found to be broken in a way that could crash a request entirely instead of failing gracefully; this has been fixed and is now backed by a test. |
| 8 | Test the entire system: unit tests, integration tests, end-to-end tests | ✅ Mostly done | 45 automated unit tests exist and all currently pass, plus a 10-question adversarial test suite specifically probing safety rules (all 10 currently pass). One end-to-end integration test exists but has a caveat: it can skip itself under certain conditions instead of always running, which is a known, documented weak spot. |
| 9 | Deploy: put it in a container, orchestrate multiple services, push to a registry, set up automatic testing on every code change | 🟡 Configured, partially exercised | Docker Compose is now actually used to run PostgreSQL (verified live, used throughout the real-data debugging in this project). The app container itself has still never been started through Docker — every real test ran the FastAPI/Streamlit services by hand instead. There is no container **registry** (a place to store and share a packaged, ready-to-run version of the app) in use. The project is now in version control and pushed to GitHub, with `.github/workflows/ci.yml` configured to run on every push — but it hasn't produced a real passing run yet, since the repository's `GROQ_API_KEY` secret still needs to be configured, and its RAGAS-scoring job is expected to fail on real quality thresholds (0.778/0.473 vs. 0.80) even once it does run. |
| 10 | Test under real load: send many requests at once, watch things break, fix them one by one | ❌ Not done deliberately, but experienced by accident | We never deliberately fired multiple simultaneous questions at the system to see what breaks. However, we *did* experience a real version of exactly this lesson: running several test questions back-to-back (not even simultaneously, just quickly) was enough to hit the free-tier's rate limit and cause failures — which we then fixed. That's the same category of problem this step warns about, just discovered the accidental way instead of the deliberate way. |
| 11 | Optimize cost and latency: caching, routing simple requests to smaller/cheaper models, measure-then-optimize-then-retest | 🟡 Partially done | There's a router that sends simple, non-climate-retrieval questions straight to the model without running the full multi-step pipeline — a real form of "route simpler requests differently." Response caching is configured but not verified working end-to-end. **What's missing:** no disciplined measure → change → re-measure cycle was followed; timing was observed informally while debugging (answers took anywhere from ~35 to ~90 seconds), not tracked as a metric over time. |

**Quick count:** of 11 steps, roughly **5 are solidly done**, **5 are
partially done with a specific, named gap**, and **1 (load testing) was
not deliberately attempted.** None were skipped silently — each gap
above is something we can point to specifically.

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
| Answer relevance & faithfulness | Does the answer actually address the question, and is every claim in it backed by the retrieved evidence | 🟡 A number is tracked and used to gate answers, but (as documented elsewhere) it's currently a simplified stand-in, not the genuine measured version |
| LLM-judge alignment (**Cohen's Kappa**, **Spearman**, **Kendall's Tau** — three different statistical ways of checking whether an AI's judgement of quality agrees with a human's judgement) | Do automated quality scores actually agree with what a human would say | ❌ Not measured |
| Tool-call error rate / steps per task | How often does a step in the pipeline fail, and how many steps does a typical question take | ❌ Not tracked as a standing metric, though individual failures are logged |
| Eval suite run across changes | Re-run the same test questions every time you change a prompt or model, to see if scores improved or got worse | 🟡 The test suites exist and can be re-run, but no history of "score before vs. after a specific change" has been kept |

### 2. Scalability — can you run it at scale?

| Metric | Plain-language meaning | Tracked here? |
|---|---|---|
| TTFT (**Time To First Token**) | How long you wait before the answer starts appearing at all | ❌ Not measured |
| ITL (**Inter-Token Latency**) | How long between each small piece of the answer as it's being generated | ❌ Not measured |
| TPS / RPS (**Tokens Per Second** / **Requests Per Second**) | How much the system can produce or handle per second | ❌ Not measured — no load testing was done (see Step 10 above) |
| Cache hit rate | What fraction of requests are answered from a saved previous result instead of doing the work again | ❌ Not measured, even though caching is configured |
| Cost per request | How much each question costs in API fees | ✅ Tracked — every request logs its actual cost, and because the free tier was used throughout, the real logged cost has been $0.00 |

### 3. Safety — does it stay within the boundaries you set?

| Metric | Plain-language meaning | Tracked here? |
|---|---|---|
| Policy violation rate | How often the system breaks its own safety rules | 🟡 Tested via a fixed set of 10 adversarial questions (currently 0 violations), but not tracked as an ongoing *rate* over real traffic |
| Refusal rate / false-refusal rate | How often the system correctly says "I can't answer that," versus how often it *wrongly* refuses a question it actually could have answered | 🟡 Correct refusals have been verified for real (e.g. regions with no data). **False**-refusal rate specifically has not been measured — we don't yet know how often the system might refuse something it shouldn't. |

The framework makes an important point here worth repeating in plain
terms: **a system that refuses every question is perfectly "safe" and
also completely useless.** Since we haven't measured the false-refusal
rate, we genuinely don't know yet whether this system leans too
cautious. That's an honest unknown, not a claim either way.

### 4. Operational reliability

| Metric | Plain-language meaning | Tracked here? |
|---|---|---|
| Error rate on failed calls | How often a call to the AI model, a tool, or the search step fails outright | 🟡 Failures are caught and logged individually so the system doesn't crash, but there's no single dashboard number saying "X% of calls failed this week" |

---

## Bottom line

**Does this project follow the 11-step path?** Substantially yes for
the first eight steps (understanding the model, backend, frontend, RAG,
partial evals, agents, reliability, testing) — each has been actually
built and, where claimed "done," verified with a real question and real
data rather than just written and assumed correct. Steps 9 through 11
(deployment, load testing, cost/latency optimization) are the weakest:
the deployment configuration exists but has never been exercised for
real, load testing never happened deliberately, and cost/latency
tuning was reactive (fixing a rate-limit crisis) rather than a
disciplined measure-optimize-retest cycle.

**Does it track the recommended metrics?** Mostly not, honestly, though
less badly than before. Of roughly 16 named metrics across the four
categories, **two** are now tracked as real numbers: cost per request,
and generation quality (RAGAS faithfulness/answer relevancy — now
genuinely LLM-judged, not a proxy). Everything else — retrieval quality
(precision@k, recall@k, MRR), LLM-judge agreement (Cohen's Kappa against
a human judge), latency, throughput, cache hit rate, and false-refusal
rate — is still either untracked or only loosely approximated.

This isn't a reason to be discouraged — it's a straightforward,
prioritised to-do list. Getting the real evaluation library working (the
RAGAS fix, see `docs/business-problem-and-alignment.md` and
`README.md`) is done. The next highest-value gap is now **operational
reliability**: there's no error-rate tracking on failed LLM/tool calls,
which is exactly the kind of gap that let a real production bug (Groq
silently renaming a model, breaking every LLM call in the pipeline) go
unnoticed until this evaluation work surfaced it by hand — see
`MAINTENANCE.md` Round 2.
