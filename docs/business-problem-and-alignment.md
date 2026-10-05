# The Business Problem, the ROI, and Does This Project Actually Solve It?

This document answers four questions in plain language, with facts
rather than impressions:

1. What problem is this project actually trying to solve, and for whom?
2. Where does that problem come from — is it real, or assumed?
3. What is the return on solving it?
4. Does what we have built so far genuinely match the problem?

Every jargon word is explained the first time it is used, in **bold**.

> **Status of the facts in this document.** Everything below marked
> "measured" was produced on **2026-10-05**, by starting the system for
> real — Postgres on a fresh volume, the UKCP18 corpus ingested, the API
> served, and a load test run against it. That was the first time this
> project had been executed end to end rather than reviewed by reading
> it, and it changed several claims these documents had been making. The
> RAGAS answer-quality scores (0.778 / 0.473) are carried over from the
> last scoring run and were **not** re-measured on that date; they are
> the only numbers here of that kind, and they are labelled where used.

---

## Part 1 — The business problem

> **Make climate information usable by people who aren't climate
> specialists, with answers they can check against a source.**

That is the whole problem statement. Two halves, both load-bearing:

- **"usable by people who aren't climate specialists"** — the
  information already exists and is public. It is not usable without
  training. The gap is interpretation, not availability.
- **"answers they can check against a source"** — an answer nobody can
  trace is not an improvement on no answer. For this audience it is
  worse, because it is actionable and unverifiable at the same time.

### Who the user is

**People who need sourced climate information for planning but lack
specialist support.**

That is the definition this project is built against, and it is
deliberately a *role*, not a sector. It covers a local-authority
planner deciding whether a new development needs flood or heat
defences, a risk analyst at a mid-size insurer, an NGO programme
officer, a sustainability lead writing a disclosure. What they share is
the thing that matters: a real decision with a climate input, a duty to
show their reasoning, and no climate scientist on call.

It specifically does **not** mean climate scientists. A specialist does
not need this system — they need the raw data, which they already have,
and they would find the guardrails here an obstacle rather than a help.

### Why these users can't just read the data themselves

The UK's national climate projections, **UKCP18** (UK Climate
Projections 2018, published by the Met Office), are free, public, and
authoritative. They are also four long technical reports written for
readers who already understand emissions scenarios, probabilistic
projections, and the difference between a reanalysis and a projection.
A planner who opens the UKCP18 Land report looking for "how much hotter
will summers get here" does not get an answer; they get a methodology.

### Why a general-purpose chatbot is not the answer either

Ask a general-purpose AI assistant instead and you get a fluent,
confident answer — sometimes a correct one, sometimes one built on an
invented statistic or a dataset that does not exist. There is no way to
tell which from the answer itself, which is precisely the failure that
matters for this audience. A planner who skips flood defences because
an AI produced a reassuring number, or an insurer who prices a policy
off a hallucinated figure, has made a real decision on fabricated
evidence, and "the AI said so" is not a defence to a **regulator** (a
government body that can require you to show your evidence and
reasoning before approving a decision).

### What this project is, then

A system that answers the same questions, but:

- It answers only from real retrieved documents and real datasets,
  never from the model's memory alone.
- It is *structurally* unable to cite a dataset that does not exist —
  the same way a form with a dropdown cannot accept an option that
  isn't listed.
- Every question and answer is written to a permanent record, so "why
  did you tell me that" has an answer months later.
- When the evidence is thin, it says so and returns nothing rather than
  guessing.

**The pitch in one line:** sourced, checkable climate answers for the
planning questions that currently get none — with a paper trail that
survives being audited.

Note what that does *not* claim. It is not "a cheaper consultant." The
constraint this addresses is that the specialist isn't available at all
(Part 2), which makes the comparison "versus nothing," not "versus an
expert." Part 3 works through why that distinction decides the entire
ROI model.

---

## Part 2 — Where the problem comes from

This is not a problem we assumed. It is the problem described in
**Williams et al.**, which sets out three findings this project is a
direct response to:

1. There are not enough climate specialists to meet demand for
   interpretation.
2. UKCP18 is hard to use without specialist help.
3. A plain chatbot over that data can invent things.

This project is a **governed** answer to the same problem: same data,
same audience, with the inventing designed out rather than warned
about. Williams et al.'s own chatbot uses UKCP18, which is also the
dataset ingested here — so the comparison is like-for-like, not an
analogy.

> **Open item for the project owner:** the full bibliographic citation
> for Williams et al. (authors, title, venue, year, DOI) is not yet
> recorded in this repository. It should be, since the business case
> rests on it. This document states the three findings as the project
> understands them; the citation needs filling in before this document
> is shown externally.

### Why the dataset does not need to change

A fair challenge to a UK-only scope is: shouldn't a climate risk system
cover more than one country?

Eventually, yes. Today, no — and deliberately. UKCP18 is the data the
paper's own chatbot uses, it is already ingested here, and it is enough
to demonstrate that the problem is solved for the UK. Proving the
mechanism works end-to-end for one region with real government data is
worth more than thin coverage of ten regions, because the mechanism —
grounded retrieval, dataset citation control, audit trail, honest
refusal — is what transfers. Adding a region is a data-loading task
(see Part 4), not an architectural one.

The project does carry some non-UK data (one Kerala rainfall file, one
global file) from earlier work. Those are retained and documented
honestly in Part 4, but they are not the proof case and are not claimed
as coverage.

---

## Part 3 — The return on solving it

Honest framing first: **this project has not been deployed, so there is
no realised ROI to report.** What follows is the model you would use to
calculate it, with every input labelled as either measured here or
supplied by the business. Do not read the structure as a result.

### The problem statement changes the shape of the ROI

This is worth being explicit about, because the obvious ROI model for a
system like this is the wrong one.

The obvious model is **cost substitution**: a specialist used to answer
this, specialists are expensive, the system is cheap, bank the
difference. That is how this project's pitch used to read — "consultant
quality answers at the cost of asking a question."

The problem statement does not support that model. Williams et al.'s
first finding is that **there aren't enough specialists** — a supply
constraint, not a price one. You cannot substitute a cost you were
never paying. For most of the questions this system is built to answer,
the honest counterfactual is not "a consultant did it more expensively."
It is **nobody did it**: the question went unasked, got answered from
memory and intuition, or waited in a queue until the planning decision
was made without it.

So the return is **capacity created, not cost avoided**, and that
changes the unit of measurement. Cost substitution is measured in
currency per query avoided. Capacity is measured in *decisions that got
a sourced climate input which otherwise would not have had one*.

| Source of value | What it actually replaces | Which model |
|---|---|---|
| **Decisions unblocked** | Questions that never got asked because no specialist was available. The primary term, directly from the scarcity finding | Capacity |
| **Traceability as admissibility** | Not a benefit — a gate. See below | Neither; it's a multiplier |
| **Specialist time released** | Where a specialist *was* answering routine UKCP18 questions, their time moves to work only they can do. Real, but secondary — it is the smaller half of a scarcity problem | Cost substitution |
| **Audit cost avoided** | The regulator-facing record is produced per query automatically instead of reconstructed by hand afterwards | Cost substitution |
| **Risk avoided** | Each decision made on a fabricated number carries a tail cost — mispriced policy, skipped defence, a disclosure that cannot be substantiated. Largest term, hardest to quantify, and the one the guardrails exist to address | Risk |

### Why traceability is a multiplier and not a line item

The second half of the problem statement — "answers they can check
against a source" — is not a feature competing for space against
accuracy, speed or cost. For this user it is an **admissibility
condition**.

A planner cannot put an untraceable number into a planning submission.
A sustainability lead cannot cite an unsourced figure in a disclosure.
An answer they cannot check is not a worse answer; it is an unusable
one. So traceability does not add to the return — it multiplies the
whole thing by 1 or by 0.

Two consequences follow, and both are load-bearing:

- **You cannot trade traceability for quality.** A more fluent,
  more on-topic, untraceable answer is worth nothing here. This is why
  a general chatbot is not a cheaper competitor to this system; it is
  not a competitor at all for this user, whatever its answer quality.
- **Anything attacking the traceability gate attacks the entire
  return,** not a percentage of it. That is precisely why the RCP8.5
  finding in Part 4 is listed as the top open defect ahead of the
  below-threshold quality scores. Low relevancy makes a usable answer
  weaker. Deleting the source's own scenario label makes a traceable
  answer uncheckable.

### What the cost side actually is, measured

These are real numbers from this project, not estimates:

| Cost input | Measured value | How it was measured |
|---|---|---|
| LLM spend per query | **$0.00 logged** | Every query records its actual cost (`litellm_cost_usd`); the free tier was used throughout, so the logged figure is genuinely zero and genuinely not representative of paid usage |
| End-to-end latency, warm | **p50 4.3s at low load, 19.4s at 16 concurrent; p95 8.4s → 23.1s** | Measured 2026-10-05 by `evaluation/load_test.py` across a concurrency ramp, LLM cache disabled |
| End-to-end latency, **first request after a restart** | **202 seconds** | Measured. The embedder and reranker load lazily and startup doesn't warm them |
| Throughput | **0.25 req/s at 1 in flight, 0.69 at 16** | Measured. 16x the concurrency returns 2.7x the throughput |
| Capacity ceiling | **~2 concurrent requests** before the free-tier token limit degrades answers | Measured: Groq ITPM limit 7,000 |
| Infrastructure | One PostgreSQL instance, one app container | `docker-compose.yml`; both verified running 2026-10-05 |

The earlier version of this table said "~35–90 seconds, observed
informally." That figure was never measured and matched neither the warm
nor the cold reality.

**The capacity ceiling is the row with real commercial consequences.**
At roughly two concurrent requests the free tier stops serving answers —
and, per Part 4, stops saying so honestly. Any ROI calculation that
assumes more than a couple of simultaneous users is costing a paid tier
that has not been priced yet.

The $0.00 figure is the one most likely to be misread. It means "the
cost tracking works and the free tier was used," not "this system is
free to run." A paid-tier cost per query is unknown and must be
measured before any ROI claim is made.

### The inputs the business has to supply

The calculation cannot be completed inside this repository, because its
terms are facts about the organisation, not the code. Under the capacity
model they are:

1. **Unmet demand** — how many planning questions per period currently
   need a sourced climate input and don't get one. Not "how many
   specialist hours do we buy," which is the cost-substitution question
   and will understate the answer, because it counts only the questions
   that got through.
2. **Value per unblocked decision** — what it is worth to have a
   planning decision carry sourced, checkable evidence rather than
   none. Often a compliance or defensibility value rather than a
   revenue one, and the honest version of this number is usually a
   range, not a point.
3. **Share of that demand this system can actually serve today.**
   Knowable, and currently unflattering: see Part 4. On the measured
   evidence the honest answer is "UK heat and general UKCP18 questions,
   and nothing else."
4. **Traceability gate** — 1 if answers are checkable against their
   source, 0 if not. **Measured at 0 under concurrent use on
   2026-10-05; both causes fixed the same day and re-verified.** The two
   defects that forced it to zero — outages reported as insufficient
   evidence, and the citation filter deleting scenario labels — are now
   closed, so answers that are returned are traceable and answers that
   are not returned say honestly why. What still holds the term below 1
   is availability rather than truthfulness: on the free tier a
   meaningful share of concurrent requests get an honest "service
   unavailable" instead of an answer, and an honest non-answer still
   isn't a usable one.

Multiply (1) × (2) × (3) × (4), subtract measured running cost, and you
have a defensible figure. Term (3) is where an optimistic case for a
system like this usually breaks. Term (4) is where this system *did*
break on 2026-10-05, and because it is a multiplier rather than a line
item, the honest ROI for concurrent use that morning was not "reduced."
It was zero.

**That is the clearest practical argument for writing traceability as a
separate term, and the fix history proves the point.** Had it been
folded into a quality score, the load-test result would have read as
"quality dipped under load" — a tuning problem, scheduled behind the
0.473 relevancy score. Written as a gate, the same result read as "the
product stopped being the product," which is the accurate description,
and it got fixed within hours instead of queued. The term ordering
decided the engineering priority, correctly.

### The strongest honest ROI statement available today

> **Revised after the 2026-10-05 load test.** The statement below used
> to read "the guardrails are the asset." That survives, but with a
> correction that matters: the guardrails are the asset *when the system
> is handling one question at a time.* Under concurrency the refusal
> guardrail stops being an asset and becomes a liability, because it
> issues confident statements about the evidence that are not true. An
> honest refusal has positive value. A refusal that misattributes an
> infrastructure failure to the climate record has negative value — it
> is the general-chatbot failure mode (a confident claim the user cannot
> check) arriving through the safety mechanism instead of around it.

**The guardrails are the asset, not the answers.** What this project has
proven, repeatedly and with real UK government data, is that it refuses
rather than fabricates and shows its sources when it answers — at
single-request load, with the two Part 4 defects outstanding.

Under the cost-substitution model that would be a weak result: the
answers score 0.473 on relevancy, so a consultant is plainly better and
the ROI looks negative. Under the capacity model it is a genuinely
positive result, because the comparison isn't against a consultant who
was never available. It is against nothing, or against a general chatbot
whose value for this user is *negative* — it produces unverifiable
answers that are indistinguishable from verifiable ones, which is worse
than no answer for someone who has to defend their reasoning.

So: a real return, from a narrower claim than the project used to make.
Not "consultant-quality answers" — this system does not deliver those
yet. Rather: **sourced, checkable, honestly-bounded climate answers for
questions that currently get none.** That claim is supported by the
measured evidence. The previous one was not.

One caveat that belongs in the same breath: that statement depends
entirely on term (4) holding, and term (4) is currently the thing with a
known defect in it.

---

## Part 4 — Does it actually do that? The measured status

### The four anti-hallucination techniques

| # | Technique, in plain terms | Status |
|---|---|---|
| 1 | Only answer from retrieved real documents, never from memory | ✅ Working — verified live on 2026-10-05: a UK heat question traversed the rulebook and returned 5 real UKCP18 pages, with page numbers |
| 2 | Dataset names can only come from a fixed, pre-approved list (a **knowledge graph** — a strict rulebook of valid dataset + region + scenario combinations) | ✅ **Working, after a fix on 2026-10-05.** It was over-enforcing destructively — deleting the emissions-scenario label the user had asked about. Fixed and re-verified: scenario labels now survive, invented dataset names are still stripped, and an unapproved-but-real dataset (`UKCP09`) is still correctly removed. See "The scenario-label defect" below |
| 3 | Every input and output is checked against a strict template (**Pydantic** schemas) so nothing can smuggle in an unexpected field | ✅ Working for the main data flowing through the system; a couple of small internal helper objects use a looser template — cosmetic, not a hallucination risk |
| 4 | If confidence is too low, refuse rather than guess | ✅ **Working, after a fix on 2026-10-05.** It used to fire the *same message* for a thin-evidence refusal and for the AI being unreachable — telling users the evidence was insufficient when it had never been read (70 of 91 queries under load). The two are now separate messages on separate branches, verified under load: false "insufficient grounding" answers went from 10 to 0. See "The outage-as-refusal defect" below |

**Technique #2 was once decorative, and was fixed.** The check meant to
catch a made-up dataset name originally scanned the answer for names
*already on the approved list*, then confirmed they were on it — so it
could never catch an invention. It now recognises dataset-shaped tokens
and classifies them, backed by 5 tests, one of which feeds it "The
SuperClimate9000 dataset reports severe flooding" and confirms the fake
name is stripped. Full account in `docs/maintenance-round-1-opus5.md`.

### The outage-as-refusal defect — fixed 2026-10-05

> **Status: fixed and verified under load the same day it was found.**
> The account below describes the defect as it was, because it is the
> most instructive thing in this document. What changed: the component
> that writes the user's message now knows about the outage flag and
> says something truthful. On the identical 16-request workload at 16
> concurrent requests, answers claiming "insufficient grounding" went
> from 10 to **zero**, and the 9 genuine outages are reported as
> outages. Seven regression tests pin it, including one asserting that
> a *real* thin-evidence refusal still says "insufficient grounding" —
> the fix must not swallow legitimate refusals into the outage message.

Found on 2026-10-05, by running the system under load for the first
time. It is the most serious defect this project has had, because it
breaks the half of the business problem that cannot be traded away.

**What happens.** The AI model this system uses is accessed on a free
tier with a cap on how much text it can process per minute. Under even
light concurrent use — about two simultaneous questions — that cap is
reached and the model refuses the call. A backup model is configured,
but it has no access key, so it fails too. At that point the system has
no model at all. It correctly scores the answer as ungrounded, and
returns its standard message:

> "Insufficient grounding to answer confidently. The retrieved evidence
> does not meet this system's faithfulness threshold, so no answer is
> returned rather than risking a low-quality or ungrounded response."

**Why that is serious rather than merely annoying.** That message is a
false statement about the climate data. It tells a planner that the
evidence was too thin to support an answer. The evidence was often
retrieved perfectly well — the UKCP18 pages were found and ranked — and
the thing that failed was an API quota. The user is given a confident
statement about the state of climate science when the actual event was
an infrastructure failure.

**Measured, not hypothesised:** of 91 queries logged during the load
test, **70 had both the primary and backup model fail**, and all 70
returned that message. Every one came back as a normal, successful HTTP
response. Average recorded faithfulness over the window: 0.213.

**Why nobody caught it in five previous review rounds.** The system
already distinguishes these two states internally — a flag called
`llm_unavailable` is set only when both models fail, and it is written
faithfully to the audit record. The monitoring check built to watch for
it fired correctly, immediately, on all 70. The failure is only in the
last step: the component that chooses the user-facing message has no
access to that flag, so it cannot say anything different. The right
information existed in the right place and was never shown to the
person who needed it.

It is also invisible from outside: the `/query` endpoint returns
thirteen fields and `llm_unavailable` is not among them. The load test
written for this round reported "0 failures" at every concurrency level
for exactly that reason, until the database was queried directly.

### The scenario-label defect — fixed 2026-10-05

> **Status: fixed and verified against the exact text that failed.**
> The live answer that came back discussing
> `[UNVERIFIED DATASET REMOVED]5-8.5` now returns `SSP5-8.5`,
> `RCP8.5`, `RCP2.6` and `SSPs` intact, while invented names like
> `SuperClimate9000` are still stripped. Two bugs needed two fixes:
> removal now matches whole words instead of substrings, and the
> rulebook's vocabulary now recognises scenario-family acronyms
> (`SSP` derived automatically from the scenario list, plus `RCP`)
> including unlisted members like `RCP8.5`. It does **not** assert that
> any RCP pathway equals any SSP pathway — that remains an owner
> decision, and is still the likeliest route to better relevancy.

Fixing technique #2 overshot, in a way that lands squarely on the UK
proof case.

Climate scenarios come in two naming generations: **RCP** labels
(Representative Concentration Pathways — RCP2.6, RCP4.5, RCP8.5), used
by UKCP18's reports, and **SSP** labels (Shared Socioeconomic Pathways —
SSP1-2.6, SSP2-4.5, SSP5-8.5), the newer equivalent used by this
system's rulebook. The rulebook lists only the *full* SSP labels. It
does not list the bare acronym `SSP`, or any RCP label at all.

So when an answer uses the phrase "SSP projections", the filter sees a
term it cannot verify as a dataset and removes it. And the removal is
done by plain text substitution, which means **every longer word
containing those three letters is rewritten too.**

Verified live. The real answer to "What is the heat risk for the UK
under SSP5-8.5?" came back as:

> "I cannot provide the specific heat risk for the UK under
> **[UNVERIFIED DATASET REMOVED]5-8.5** … the question asks for
> **[UNVERIFIED DATASET REMOVED]5-8.5** … while the text mentions that
> **[UNVERIFIED DATASET REMOVED]s** were used for CMIP6"

The scenario the user asked about is destroyed in the reply. Three
things follow:

- **It is a false positive, not a hallucination.** The guardrail is too
  strict, not too loose. Nothing invented got through.
- **It is a direct hit on the stated business problem.** "Answers they
  can check against a source" cannot survive a filter that deletes the
  source's own vocabulary from the answer.
- **There are two independent bugs here**, needing separate fixes: the
  rulebook is missing the bare acronyms, and the removal mechanism
  rewrites substrings instead of whole words. The second would damage
  any short term that ever gets flagged, regardless of climate
  vocabulary.

`MAINTENANCE.md`'s Round 1 write-up lists `RCP8.5` as "ignored —
scenarios and ordinary terms, not dataset claims." That was the intent;
it is not what the code does. Recorded as Round 6, finding 1.

### The three regulatory questions

**Q1 — "Does it behave correctly before it goes live?"**
⚠️ **The honest answer got worse on 2026-10-05, because the tests were
re-run and the system was load-tested.**

The suite itself is healthy: **52 unit tests pass in 13–19 seconds**
(verified, not carried over — the earlier "45 tests" figure was stale),
plus 4 integration tests, plus a **red team** suite of 10 deliberately
hostile questions (prompt injection, jailbreak, PII, hallucination bait,
financial and legal traps) recorded as all handled correctly. The
guardrails did hold under concurrent load — tier-1 blocks, injection
blocks and coverage-gap refusals all fired correctly across 80+
concurrent requests.

But the integration tests **passed during the same window in which 70 of
91 queries were failing completely.** Three of the four only exercise
paths that never call the AI model at all; the fourth skips itself
conditionally and then checks only that two fields exist in the audit
record, nothing about the answer. So they take 3m34s to 9m23s (measured
twice — the runtime is dominated by LLM rate-limit backoff) and
cannot tell a working system from a broken one.

That is the real answer to Q1 today: the tests pass, and passing tests
do not currently mean the system behaves correctly. A regulator would
be entitled to ask what the suite is for.

**Q2 — "Can you explain any specific past answer to a regulator on
demand?"**
✅ Yes, verified. The full record for a previously-asked question was
retrieved by ID and showed the document pages used, the path taken
through the rulebook, the answer, and a confidence score. One honest
caveat, already handled: the per-query faithfulness number in that
record is a fast proxy (does grounded evidence exist?), not the real
LLM-judged measurement, and every record carries a
`faithfulness_measured: false` flag saying so explicitly.

**Q3 — "Would you find out about a quality problem before your
customer does?"**
✅ **Yes — now verified against a real incident, which is the strongest
result of the 2026-10-05 run.** The load test caused a genuine outage,
and all three monitoring checks detected it correctly and unprompted:

- **LLM outage check:** 70 occurrences in 15 minutes → alert fired
- **Faithfulness drift check:** 0.213 average over 91 queries, against
  a 0.80 threshold → alert fired
- **Per-region segment check:** Global 0.000 (15 queries), Kerala 0.076
  (17), UK 0.306 (59) → alert fired on all three

This is the one claim in this document that came out of the live run
looking *better* than it was written. The monitoring is real and it
works on real incident data.

Three caveats keep this from being a clean ✅:

1. **Nothing schedules it.** Running it is a manual command, so "would
   you find out" currently means "if someone remembers to look."
2. ~~**The documented command doesn't work.**~~ Fixed 2026-10-05 —
   the script now bootstraps its import path like its four siblings, so
   `python evaluation/online_monitor.py` works as documented.
3. **The alert goes to a placeholder.** Every alert above was addressed
   to "TODO: named human owner."

So the detection is proven; the delivery is not. The system knew within
seconds that it was failing 77% of its queries, and had no one to tell.

### The original specification's 28 behaviours

The specification this project was built against listed 28 specific
behaviours alongside the three regulatory questions. Rather than
reproduce all 28 here, the honest summary is unchanged from previous
reviews: **all 28 are implemented**, and most have been exercised with
real data and real questions rather than written and assumed to work.
Two remain placeholders exactly as originally planned — a named human
owner for emergency decisions (the mechanism works, the name is blank;
item 9 in Part 5), and compound questions such as "combined flood and
heat risk for the UK" (item 10).

"Implemented" is doing real work in that sentence and should not be
read as "verified." The RCP8.5 finding above is a behaviour that is
implemented, tested, and wrong at the edges — which is the general
caution to apply to a 28-of-28 count.

### What the measured answer quality actually is

From the last real scoring run against `evaluation/test_dataset.json`:

| Metric | Score | Threshold | What it means |
|---|---|---|---|
| Faithfulness | 0.778 | 0.80 | Claims are mostly backed by the retrieved evidence. London scored 1.0; the UK answer 0.556 |
| Answer relevancy | 0.473 | 0.80 | The real weak spot — answers are honest but not tightly on-topic |
| Context precision | 0.0 | 0.80 | Not a real signal. It needs a genuine reference answer per question, and `test_dataset.json` only carries placeholder `pass`/`fail` labels |

Below threshold on two of three. This is the system's real current
quality level, not a placeholder or a broken script.

**The relevancy number has a visible cause.** Both scoring UK answers
spend their length explaining why they *cannot* answer precisely — the
London answer opens "I cannot give a specific quantitative projection
for heat risk in London under SSP2-4.5," then correctly explains that
the retrieved text covers the UK and South East England but not London
specifically, and covers RCP8.5 and RCP2.6 but not SSP2-4.5. Every one
of those statements is true and well-grounded. It is also not what the
user asked. The system is being scored honest-but-unhelpful, and the
SSP/RCP vocabulary mismatch described above is part of why: the test
questions ask in SSP labels, the UKCP18 source answers in RCP labels,
and nothing in the system bridges the two.

That is a more useful diagnosis than "relevancy is low," and it points
at a specific fix (a scenario-equivalence mapping) rather than a vague
one (tune the prompt).

### What is actually loaded, by region

| Region | Real evidence loaded | What was verified |
|---|---|---|
| **UK** (the proof case) | ✅ 4 UKCP18 reports — Land (241 chunks), Marine (154), Overview (92), starters guide (30) = **517**, re-ingested and counted on 2026-10-05 | Real questions retrieved the right pages and produced grounded, if over-hedged, answers. The only region with retrieved context in the evaluation run. No page needed OCR fallback |
| London | ✅ Covered by the same UKCP18 corpus | Retrieved 5 chunks; scored 1.0 faithfulness |
| Kerala | ✅ One real ERA5 rainfall file | The analysis agent computed a real monsoon rainfall figure and a real chart. **Caveat:** ERA5 is historical reanalysis, not a future projection — the knowledge graph's `SSP5-8.5` tag on this entry is a label of convenience, not a claim that the numbers are scenario-modelled (`MAINTENANCE.md` backlog item 1). In the retrieval evaluation it correctly returned "insufficient grounding" |
| Global | ✅ One real CMIP6 file | Same — a real number and chart, not a guess |
| Everywhere else — Mumbai, South Asia, Southeast Asia, East and West Africa | ❌ No real evidence | Correctly returns "insufficient grounding." CORDEX has no local data at all despite appearing in the rulebook |

**Measured on 2026-10-05, a mechanism correction.** The refusals for
Kerala and Mumbai are not caused by "no documents for that region" —
they are caused by the dataset tag. Every one of the 517 chunks is
tagged `dataset=UKCP18` with region and scenario left blank. The
retrieval filter tolerates a blank region but not a *mismatched*
dataset, so:

| A question resolving to | Chunks it can search, of 517 |
|---|---|
| UKCP18 (any UK question) | **517** — the filter narrows nothing |
| CMIP6 (Mumbai, Global) | **0** |
| ERA5 (Kerala) | **0** |

The outcome is the same honest refusal, so nothing in the behaviour
table above changes. But it means the system is effectively
UKCP18-or-nothing at the retrieval layer, and the "SQL pre-filter
narrows the search space ~50x" claim that used to appear in `README.md`
was never true of this corpus. Corrected there; recorded as Round 6,
finding 7.

The measured version of that table, from the evaluation run: **of 10
test questions, exactly 2 retrieved any evidence at all — London and
the UK, both from UKCP18.** The other 8 refused or were blocked, every
one of them correctly.

Read in isolation that looks like failure. Read against the business
problem it is the core claim holding up: the system does not fake
coverage it does not have. The honest scope statement is "UK, via
UKCP18, with answer quality still below target" — and that is exactly
the scope Part 2 argued for.

---

## Part 5 — What is not done

Ordered by how much it blocks the business problem. Reordered on
2026-10-05: the top two items are both new, both found by running the
system, and both attack traceability rather than quality — which under
the ROI model in Part 3 makes them more serious than anything that was
on this list before.

1. ~~**A model outage is reported as insufficient evidence**~~ —
   **FIXED 2026-10-05 and verified under load.** On the identical
   16-request workload at concurrency 16, answers claiming "insufficient
   grounding" went from 10 to **zero**, and the 9 genuine outages are
   now reported as outages. Every refusal the system now issues is
   either a real coverage gap, a Tier-1 block, a clarification request,
   or an honestly-labelled service failure. **Nothing lies about the
   evidence any more** — which means the traceability gate in Part 3 is
   no longer forced to 0 by this defect.
2. ~~**The citation filter destroys scenario labels by substring**~~ —
   **FIXED 2026-10-05.** The live answer that came back as
   `[UNVERIFIED DATASET REMOVED]5-8.5` now returns `SSP5-8.5`, `RCP8.5`
   and `RCP2.6` intact. Note the fix does *not* claim any RCP↔SSP
   scientific equivalence; that is still an open owner decision, and it
   is still the likeliest route to improving answer relevancy.
3. **`/query` doesn't expose `llm_unavailable`**, so no caller can tell
   an outage from a refusal. This is what made defect 1 invisible for
   five review rounds and made the load test's own report wrong.
   **Same root cause, second symptom: LangSmith reported the entire
   outage as 100% successful** — 100 spans, every one green, logged
   during the incident, because the LLM calls are not traced at all.
   Diagnosing the incident required the audit table and raw server
   logs; the tracing dashboard would have said "all healthy." Fixing
   this is cheap (wire litellm's LangSmith callbacks, trace retrieval
   and the guardrails, set span status from `llm_unavailable`) and it is
   what makes every other defect on this list findable next time.
4. **No fallback model is actually usable.** `LITELLM_FALLBACK_MODEL`
   points at OpenRouter with no key configured, so every primary
   failure becomes a total outage. Either configure a key or point the
   fallback at a second Groq model.
5. **The analysis agent fails on every UK query, and says so inside the
   answer.** UKCP18 has no NetCDF files, so the agent always errors, and
   the failed result is passed into the answer prompt where the model
   cites it as evidence of insufficiency. A failed tool result should
   never enter the grounding context.
6. **No API authentication.** Anyone who can reach the FastAPI endpoint
   can use it. Confirmed by inspection: no auth of any kind in
   `main.py`.
7. **Answer quality below its own gate** — 0.778 faithfulness, 0.473
   relevancy against a 0.80 bar. Needs retrieval and prompt work, and
   likely an SSP↔RCP mapping.
8. **Retrieval quality is unmeasured.** Precision@k, recall@k, MRR —
   none tracked. The biggest genuine measurement hole, but it has to
   come *after* defects 1 and 2: any retrieval number computed while
   most queries return a canned refusal would measure the rate limit,
   not the retrieval.
9. **Cold start is 202 seconds.** Models load lazily on first request
   and startup doesn't warm them. Fix is a warm-up call in the
   `lifespan` hook.
10. **The integration suite can't detect failure** — passes green
    through a 77% outage, in 3m34s–9m23s. See Q1 above.
11. **Throughput scales badly and the real ceiling is unknown.** 16x
    concurrency buys 2.7x throughput; the free-tier token limit is hit
    from ~2 concurrent requests, which masks the database pool and
    subprocess limits entirely. The next load test should stub the LLM
    layer to find those.
12. **CI has never completed a real run.** The workflow is configured
    and the repository is pushed, but the `GROQ_API_KEY` secret is not
    set, so a push fails immediately rather than testing anything.
13. **Nothing schedules the monitors.** Running them by hand now works
    (the broken command was fixed), but no cron or cloud scheduler
    invokes them, so "would you find out" still means "if someone
    remembers to look" (Q3 above).
14. **No named alert owner.** `config.ALERT_OWNER` is a placeholder —
    every alert in the live incident was addressed to "TODO: named
    human owner." A business decision.
15. **Regulatory PDF export** and **uncertainty ranges** — both marked
    future work from the start, both still future work.
16. **One accepted scientific trade-off**: Kerala's ERA5-under-SSP5-8.5
    entry, documented above and in `MAINTENANCE.md`. Reviewed and
    deliberately kept, not an oversight.

**~~Never load-tested~~** — closed 2026-10-05. It was item 4 on this
list for five review rounds, and closing it produced items 1, 3, 4, 5,
9, 10 and 11.

---

## Bottom line

**Does the project match the business problem?** The architecture does,
and it is genuinely built: grounded retrieval over real UK government
data, dataset citation control, a complete audit trail per query, and
honest refusal when evidence is thin — all demonstrated live rather than
assumed. The monitoring is better than most systems of this size have,
and proved it by catching a real incident unprompted.

**On the morning of 2026-10-05 the answer was no, for two specific
reasons — and both were fixed by that afternoon.**

The two defects that broke it were:

- *"Answers they can check against a source"* — under concurrent use,
  70 of 91 queries told the user the evidence was insufficient when the
  real cause was a rate-limited API. Not a traceable answer: a
  confident, untraceable claim about the climate record, which is
  precisely the failure this project exists to prevent, arriving
  through the safety mechanism rather than around it.
- *"Usable by people who aren't climate specialists"* — one answer
  returned the user's own requested scenario as
  `[UNVERIFIED DATASET REMOVED]5-8.5`.

**Both are now closed and re-verified under the same load.** False
"insufficient grounding" answers: 10 → 0. Scenario labels: intact. Every
refusal the system issues is now a genuine coverage gap, a Tier-1 block,
a clarification request, or an honestly-labelled service failure.

**What that leaves.** The remaining gaps (Part 5) are real but of a
different character — they are about *capability and availability*, not
about telling the truth:

- On the free tier, a meaningful share of concurrent requests get an
  honest "service unavailable" rather than an answer. Honest, but not
  useful. This is a paid-tier decision plus the input-token reduction
  work, not a code defect.
- Answer relevancy is still 0.473 against a 0.80 bar — the answers that
  do arrive are faithful and well-sourced but over-hedged. The likeliest
  single improvement is the RCP↔SSP scenario mapping, which is a
  scientific judgement for the owner.
- Retrieval quality is still unmeasured, and that measurement is now
  *unblocked* — it was meaningless while most queries returned a canned
  refusal.

**The honest status line:** a well-architected, well-monitored system
that now tells the truth about its own failures, answers UK questions
from real government sources with page numbers, and is limited mainly by
a free-tier quota and over-cautious phrasing. Not yet ready for someone
to act on an answer unreviewed — but the reasons are now ordinary
engineering and one scientific decision, rather than the system making
false statements about the evidence.
