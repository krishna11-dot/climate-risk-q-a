# What We Did, Step by Step, in Plain Language

This document is for anyone — no technical background assumed. Every
technical word is explained in **bold** the first time it appears. If
you read only one document about this project, read this one.

It answers nine questions:

1. What problem were we trying to solve?
2. What did we build?
3. What did we actually do on 5 October 2026, and why?
4. What broke, and why does each thing matter?
5. Did we solve the business problem?
6. What did we fix, and how do we know it worked?
7. Was the cleanup done by a different AI model?
8. What about CI/CD — the robot that checks every code change?
9. What tests exist, and do they earn their keep?

---

## 1. The problem, in one sentence

> **Make climate information usable by people who aren't climate
> specialists, with answers they can check against a source.**

**Who needs this:** people who need sourced climate information for
planning but have no specialist to ask. A council planner deciding
whether a new housing development needs flood defences. An insurance
analyst pricing risk. A sustainability manager writing a report their
regulator will read.

**Why they're stuck.** The UK's official climate projections —
**UKCP18** (UK Climate Projections 2018, published by the Met Office)
— are free and public. They are also four long technical reports
written for scientists. A planner who opens them looking for "how much
hotter will summers get here" doesn't find an answer; they find a
methodology.

**Why they can't just ask ChatGPT.** A general AI assistant will answer
confidently whether or not it knows. Sometimes it invents a statistic.
Sometimes it invents the name of a scientific dataset that doesn't
exist. You cannot tell which from reading the answer. For someone who
has to defend their reasoning to a regulator, a confident answer they
can't verify is worse than no answer at all.

**So the whole point of this project** is the second half of that
sentence: *answers they can check against a source*. Not just correct
answers — **traceable** ones.

---

## 2. What we built

> For the fuller version — a walkthrough of one question travelling
> through the system, plus the *reason* each piece exists and what would
> go wrong without it — see "How it works, and why it's built this way"
> in `README.md`. It is written for the same reader as this document.


A system that answers climate questions, where:

- It reads real documents and quotes them. It is not allowed to answer
  from memory.
- It cannot invent a dataset name. There's a fixed list of approved
  data sources, and anything not on that list gets stripped out of the
  answer.
- Every question and answer is written into a permanent record, so
  months later you can ask "why did it say that?" and get a full
  reconstruction.
- If the evidence isn't good enough, it says so instead of guessing.

The machinery behind it, in plain terms:

| Piece | What it does | The jargon word for it |
|---|---|---|
| A reader | Chops the four UKCP18 PDFs into 517 small searchable pieces | **Chunking** |
| A searcher | Finds the handful of pieces most relevant to your question | **Retrieval**, or **RAG** (Retrieval-Augmented Generation) |
| A rulebook | Lists which data sources are valid for which region and scenario | **Knowledge graph** |
| A writer | Turns the found pieces into a readable answer | The **LLM** (Large Language Model — the AI that writes text) |
| Four safety checks | Block bad questions, block ungrounded answers, strip invented sources, refuse when evidence is thin | **Guardrails** |
| A logbook | Records every question, every source used, every score | **Audit trail** |
| A watchman | Checks the logbook for signs of trouble and raises an alarm | **Monitoring** |

---

## 3. What we did on 5 October 2026, and why

### The reasoning: why we did this at all

For five previous review rounds, this project had been checked by
**reading** it — reading the code, and reading files it had produced
earlier. That found real bugs. But reading has a ceiling.

Reading the code tells you what the system is *meant* to do. The old
files tell you what it did *once*. Neither tells you what it does when
it's running and busy. So this time we switched it on.

### Step by step, what actually happened

**Step 1 — Start the database.** We started the storage system
(**PostgreSQL**, the database that holds the 517 document pieces). It
installed itself correctly and applied all its own updates. ✅

**Step 2 — Load the climate reports.** We fed in the four UKCP18 PDFs.
It produced **exactly 517 pieces** — Land report 241, Marine 154,
Overview 92, starter's guide 30. This mattered because three of our
documents had been claiming "517" for months without anyone having
re-checked it. The number was right. ✅ Took about 4 minutes.

**Step 3 — Start the service and ask it a real question.** We asked:
*"What is the heat risk for the UK under SSP5-8.5?"* It worked through
the rulebook correctly, found 5 real UKCP18 pages, and gave page
numbers. The plumbing genuinely works. ✅

**Step 4 — Fix the broken workshop.** Before we could run the automated
tests, we found the project's development environment was broken. The
project folder had been moved at some point, and a configuration file
still pointed at the old location under a different user account. The
tests could not run at all. We repaired it. This had gone unnoticed for
five review rounds — because nobody had tried to *run* anything.

**Step 5 — Run the automated tests.** **52 tests pass in about 15
seconds.** (Our docs had been saying "45 tests," which was out of
date.) ✅

**Step 6 — The load test.** See below.

**Step 7 — Check the watchman.** We ran the monitoring checks against
the real logbook. All three alarms fired correctly. ✅

**Step 8 — Check the trace recorder (LangSmith).** See section 5.

---

## 4. What a load test is, and what we found

### What a load test is, in plain language

Everything up to now asked the system **one question at a time**. A
real service has several people using it at once.

A **load test** means deliberately sending many questions
simultaneously and watching what happens. Three things get measured:

| What we measure | What it means in plain terms |
|---|---|
| **Latency**, as P50 / P95 / P99 | How long people wait. P50 = the time half of people wait. P95 = the time 95% wait within. **P99 is the unlucky 1%** — and those are the people who complain |
| **Throughput** | How many questions the system finishes per second |
| **Errors, split by cause** | Not "how many failed" but *why* each one failed |

**Why split errors by cause rather than just counting them?** Because
"7% of requests failed" tells you nothing you can act on. Four
completely different things can fail here — the AI provider's usage
limit, the database running out of connections, a calculation step
timing out, or the AI being unreachable entirely — and each needs a
different fix. One number hides which problem you have.

**And the most important point about the goal:** a load test is not
there to prove the system is fast. **It is there to find where it
breaks.** A load test where nothing fails hasn't told you anything
except that you didn't push hard enough.

### What we ran

We sent the same batch of 16 questions five times over, each time
allowing more of them to run simultaneously — first 1 at a time, then
2, 4, 8, and finally all 16 at once.

**Why keep the questions identical each time?** So that the only thing
changing is the crowding. Our first attempt accidentally used different
questions at each level, which made the results meaningless — we were
comparing different workloads and calling it a concurrency effect. We
caught that and re-ran it properly. (We also found and fixed a genuine
mistake in our own test tool, which was firing everything at once
regardless of the setting.)

### The results

| People at once | Average wait | Unlucky wait | Questions finished per second | Errors |
|---|---|---|---|---|
| 1 | 4.3s | 8.4s | 0.25 | 0 |
| 2 | 5.1s | 10.1s | 0.40 | 0 |
| 4 | 7.8s | 20.7s | 0.49 | 0 |
| 8 | 7.4s | 23.7s | 0.59 | 0 |
| 16 | 19.4s | 23.1s | 0.69 | 0 |

**Reading 1 — it doesn't scale well.** Going from 1 user to 16 users
(16 times the demand) only got us 2.7 times the work done, and the
average wait got 4.5 times worse.

**Reading 2 — the first question after startup takes 202 seconds.**
Nearly three and a half minutes. The AI components that read documents
are only loaded when first needed, so the very first person after every
restart pays that cost. Our documentation had said answers take "35 to
90 seconds," a figure that matched neither the cold reality (202s) nor
the warm one (2–20s).

**Reading 3 — and this is the one that matters.** Look at the Errors
column: zero, every time. Now look at what the answers actually said:

| People at once | Real answers given | "I don't have enough evidence" |
|---|---|---|
| 1 | 4 | 6 |
| 16 | **0** | **10** |

**Same questions. Zero errors. And the system stopped answering.**

---

## 5. The errors we found, each explained simply

> **Before you read this list: Errors 1, 2 and 3 are now FIXED.** They
> were found and repaired on the same day, and the repairs were
> re-tested under the same load that exposed them. Section 9 at the end
> shows the before/after. The descriptions below are kept as they were
> found, because *how* they happened is the most useful part.

### Error 1 — the system blamed the climate data for its own breakdown ✅ FIXED

**The most serious thing we found.**

The AI writing the answers is used on a free plan, which has a cap on
how much text it can process per minute. Send two questions at once and
that cap is hit. A backup AI is configured — but it has no access key,
so it fails too. At that point the system has no AI at all.

And here is what it tells the user:

> *"Insufficient grounding to answer confidently. The retrieved evidence
> does not meet this system's faithfulness threshold."*

In plain terms: **"the climate evidence isn't good enough to answer
you."**

That is not true. The climate evidence was usually found perfectly
well. What failed was a billing limit.

**Measured: 70 out of 91 questions.** Every one looked like a normal,
successful response.

**Why this is the worst possible bug for this specific project.** The
entire promise is "answers you can check against a source." This bug
makes the system issue a confident, false statement about the state of
climate science — which is *exactly* the failure we built all the
guardrails to prevent. It arrived through the safety mechanism instead
of around it. A planner reading that message would reasonably conclude
the climate record is too thin to support a decision.

**The strange and hopeful part:** the system already *knew*. Internally
it records the difference between "no evidence" and "the AI was down",
correctly, every single time. The alarm spotted all 70 within seconds.
The only broken link is the very last one — the part that writes the
user's message cannot see that information. The right fact was in the
right place, and was never shown to the person who needed it.

### Error 2 — it deleted the scenario the user asked about ✅ FIXED

We asked about **SSP5-8.5** (a standard label for a high-emissions
future scenario). The answer came back discussing
**`[UNVERIFIED DATASET REMOVED]5-8.5`**.

Here's what happened. The anti-invention guard looks for anything
shaped like a data-source name. It decided the three letters `SSP`
looked like an unapproved source and removed them. And because it
removes text by simple find-and-replace, it also rewrote **every longer
word containing those three letters** — including the scenario name
itself.

**Why it matters:** nothing fake got through. This is the *opposite*
failure — a guard being too aggressive. But the effect on a reader is
serious, because the answer keeps the number ("UK summers warming by up
to 5.4°C") and deletes the label saying *under which scenario*. The
label is what makes the number mean anything.

### Error 3 — the system can't tell anyone outside that it's broken ✅ FIXED

The internal "the AI was unreachable" flag never leaves the building.
The response sent back to a caller contains thirteen pieces of
information, and that flag isn't one of them.

**Why it matters:** this is *why* errors 1 and 2 went unnoticed. Our own
load test reported "0 failures" at every level — correctly, based on
what it could see — while 70 queries were failing. We only discovered
the truth by querying the logbook database directly afterwards.

### Error 4 — the calculation step fails on every UK question, and says so inside the answer — still open

The rulebook sends UK questions to a calculation tool that needs a
numerical data file. UKCP18 is PDFs — there is no such file. So the
tool fails every time, on the only region we have data for.

Worse, the failure message is handed to the AI as if it were evidence,
and the AI then cites it: *"the metadata indicates analysis failed…
confirming that the specific numerical projections were not
successfully retrieved."*

**Why it matters:** an internal configuration problem is being presented
to the user as a fact about climate science. A failed internal step
should never become part of the evidence.

### Error 5 — the documented command doesn't work — still open

Our own README tells you to run the monitoring with a particular
command. That command fails immediately with a "module not found" error.
It needs an extra setting to work. Small, but it means the instructions
we wrote were never tested.

### Error 6 — the search filter doesn't do what we claimed — docs corrected, code unchanged

We had documented that a first-pass filter narrows the search from
"~10,000 pieces to ~200", roughly 50 times smaller. We measured it:

| A question about | Pieces it can actually search (of 517) |
|---|---|
| The UK | **517** — filters out nothing |
| Mumbai | **0** — filters out everything |
| Kerala | **0** — filters out everything |

It's not a narrowing filter, it's an on/off gate. Every one of the 517
pieces is labelled "UKCP18" and nothing else, so a question about any
other data source matches nothing.

**Why it matters:** the honest behaviour is unchanged — asking about
Mumbai correctly says "I don't have evidence." But the explanation in
our docs was wrong, and "~50x smaller search space" was an aspiration
written up as a measurement. Now corrected.

### Error 7 — the tests pass even when the system is broken — still open

The four deeper "does the whole thing work" tests **passed** during the
same period when 70 of 91 questions were failing.

Three of them only test paths that never involve the AI at all. The
fourth skips itself under certain conditions, and then only checks that
two labels exist in the logbook — it never looks at the answer.

**Why it matters:** those tests take between 3.5 and 9 minutes to run
and cannot tell a healthy system from a badly broken one. That's the
clearest possible case of a test that doesn't justify its existence.

---

## 6. LangSmith — yes, it was there, and it reported everything as fine

**What LangSmith is:** an **observability** tool. Observability means
being able to see inside a running system — not just its final answer,
but every step it took on the way. LangSmith records each step as a
**trace** (the full journey of one question) made of **spans**
(individual steps within it).

**Was it working?** Yes, genuinely. We checked by querying it directly:
the account authenticates, the project `climate-risk-agent` exists, the
regional endpoint is configured, and it received traces during our run.

**What it recorded:** 100 steps.

| Step recorded | How many |
|---|---|
| supervisor (the coordinator) | 41 |
| LangGraph (the overall flow) | 20 |
| kg_agent (the rulebook checker) | 15 |
| analysis_agent (the calculator) | 12 |
| rag_agent (the document searcher) | 12 |

**And all 100 are marked "success". Not one records an error.**

Recorded during the exact window when 70 of 91 questions were failing.

### Why — and this is the important part

**There are no AI-call steps in the traces at all.** Every one of the
100 recorded steps is a "chain" (a coordination step). Not a single one
is an AI call. The function that actually talks to the AI was never
wired up to the trace recorder, and neither was the connector's own
built-in reporting.

So the 89 rate-limit rejections and 178 authentication failures — the
real events — have **no step to appear in**. The traces can't show a
failure in a call they never recorded.

Second reason: the system is deliberately built never to crash. When the
AI fails, the code returns an empty result instead of raising an error.
That's correct production behaviour — but it means each step finishes
tidily, and LangSmith marks it successful.

**Only four functions in the whole project are being traced**, all of
them top-level coordinators. Not traced: the AI calls (where the outage
happened), the four-stage document search (where search quality would
show up), and all four safety guards (including the one that destroyed
`SSP5-8.5`).

**The three places our real bugs live are exactly the three places with
no visibility.**

### The proof, and the lesson

When we diagnosed this incident, we did not use LangSmith. We used the
logbook database and the server's raw error output. LangSmith
contributed nothing.

Had it been our only window into the system, the honest conclusion from
the dashboard would have been **"100 steps, all green."**

This is the practical version of a well-known point about debugging
these systems: *if you only see the final answer, you don't know where
things went wrong.* Our situation is a step worse than that — we had a
dashboard, and it showed green through a 77% failure rate. **A tracing
setup that reports success through an outage is worse than having none,
because it actively provides false assurance.**

What to fix, in order: connect the AI calls to the trace recorder so
failures become visible steps; trace the search and the guards; and make
a step's status reflect the "AI was unreachable" flag, so a trace fails
when the system fails.

---

## 7. Why we looked where we looked — the debugging reasoning

There's a standard way to debug this kind of system when it gives bad
answers: **trace what happened between the user's question and the
information that actually reached the AI.** Work through the chain in
order, because a failure early on makes everything after it look
broken.

Here's that checklist against what we actually found:

| The standard question | What we found |
|---|---|
| Did the system pick the right tools? | 🟡 Mostly — but it sends UK questions to a calculator that cannot serve them (Error 4) |
| Is the **metadata filtering** (narrowing by labels like region and data source) correct? | ❌ **No.** It's an on/off gate, not a filter, because only one label was ever applied (Error 6) |
| Did the search fetch the right pieces? | ✅ Yes — real UKCP18 pages with correct page numbers |
| Is the **chunk quality** good (are the pieces sensibly sized and meaningful)? | ❓ Unknown — never measured |
| **Recall:** of all the relevant pieces that exist, what share did we find? | ❓ Unknown — never measured |
| **Precision:** of the pieces we fetched, what share were actually relevant? | ❓ Unknown — never measured |
| Right pieces fetched, but the answer is still wrong — was there conflicting information? | ✅ **Yes, and it's real.** The source documents use one scenario naming system (RCP labels); our questions use the newer one (SSP labels). Nothing bridges them, so the AI correctly reports a mismatch and declines to answer |
| Were the prompt instructions clear? | 🟡 Partly — the failed calculator result is passed in as if it were evidence (Error 4) |
| Does the metadata stay attached to each piece? | ✅ Yes — source document, page number and section travel with every piece |

**Why this ordering matters, concretely.** We nearly drew the wrong
conclusion. The quality score for "is the answer on-topic" was a
mediocre 0.473, and the obvious reading is "the AI writes poor answers,
improve the instructions." Working through the chain in order showed
something different: the answers were *honest and well-sourced*, and
were being dragged down by a naming mismatch in the source documents, a
guard deleting words, and a calculator failing. Those need completely
different fixes from "improve the instructions."

**The two measurement gaps in that table — recall and precision — are
the biggest genuine hole in this project.** Right now we cannot tell
"we fetched the wrong pages" apart from "we fetched the right pages and
wrote a poor answer from them," and those need opposite fixes.

But there's a sequencing point we learned the hard way: **those
measurements have to wait until Errors 1 and 2 are fixed.** Any search
quality figure calculated now would mostly be measuring the rate limit,
not the search.

---

## 8. So did we solve the business problem?

Honest answer, in three parts.

### What is genuinely solved

**The hard part is built and proven.** A system that reads real
government climate documents, quotes them with page numbers, keeps a
complete permanent record of every answer, refuses to invent data
sources, and admits when it has no evidence — that exists, it runs, and
we watched it work on real UK data.

**The monitoring is genuinely good**, and it was the one thing that came
out of this looking *better* than our documents claimed. It caught a
real incident, unprompted, within seconds, across all three of its
alarms. That's the regulator's question — *"would you find out before
your customer does?"* — answered with evidence rather than intention.

### What was broken that morning — and fixed that afternoon

Two things were failing, and both halves of the problem statement were
affected:

*"Answers they can check against a source"* — with more than about two
people using it at once, the system told users the climate evidence was
insufficient when the real cause was a billing limit. That isn't a
traceable answer. It's a confident, unverifiable claim about climate
science — the precise thing this project exists to prevent.

*"Usable by non-specialists"* — one answer returned the user's own
requested scenario as `[UNVERIFIED DATASET REMOVED]5-8.5`.

**Both are now fixed and re-tested under the same load** (section 9).
False "not enough evidence" messages went from 10 to zero; scenario
labels survive. The system no longer makes untrue statements about the
climate record.

### What is still not solved

The remaining gaps are a different kind of problem — they're about
*capability and availability*, not about telling the truth:

- **It runs out of free allowance.** With several people at once, a fair
  share of requests get an honest "our service is unavailable" instead
  of an answer. Honest, but not useful. That's a paid-plan decision plus
  some work to send less text per question.
- **The answers are over-cautious.** They're accurate and well-sourced
  but hedge heavily, scoring 0.473 where we want 0.80. The most likely
  single improvement is deciding how the old and new scenario naming
  systems correspond — a scientific judgement for you.
- **We still can't measure whether the search finds the right pages.**
  The biggest genuine unknown. Importantly, this measurement is now
  *possible* — it was meaningless while most questions returned a canned
  refusal.

**So: not yet ready for someone to act on an answer without a human
checking it.** But the reasons are now ordinary engineering and one
scientific decision — not the system telling people things that aren't
true.

### Why that's a better position than it sounds

None of what's broken is architectural. There's no redesign needed.

- The system already knows when it's in outage, records it correctly,
  and alarms on it. One component just can't see that flag.
- The scenario-deletion bug is a find-and-replace that should be
  matching whole words.
- The 202-second cold start is a missing warm-up step.
- The invisible-outage problem is a missing field in a response, and a
  missing trace connection.

These are small, well-understood fixes to a sound design — and the
measuring equipment needed to prove they worked is already built and
already proven to work.

**The honest one-line status:** a well-built, well-monitored system that
understands its own failures correctly and has a broken final step in
communicating them. Closer to usable than the list of errors above makes
it look — but not usable yet.

### The single most useful thing we learned

For five rounds this project was reviewed by careful reading, and the
reviews were good — every bug they found was real. But reading the code
never surfaced seven of the nine problems above, and understated the
other two.

All nine appeared within about an hour of switching the system on and
putting it under pressure.

> Reading a system tells you what it's meant to do.
> The files it left behind tell you what it did once.
> **Only running it tells you what it does.**

"Load test" was on the to-do list for five rounds. The reason to finally
do it turned out to have nothing to do with speed.

---

## 9. What we fixed, and proof that it worked

Three of the seven errors were repaired the same day they were found.
Here is what changed and how we know it worked.

### Fix 1 — the system no longer blames the climate data for its own breakdown

The part that writes the user's message can now see the "the AI was
unreachable" flag, and says something truthful instead. A user hitting an
outage now reads:

> "No answer was generated: the language model service was unavailable
> (both the primary and fallback models failed). This is a system
> failure on our side, **NOT a judgement about the climate evidence** —
> the underlying data may be perfectly adequate and was not assessed.
> Please retry."

**One subtlety that mattered.** We had to put this check *before* the
existing "is the evidence good enough?" check. An outage always scores
zero on evidence quality, so in the other order the new message would
never have been reachable and the bug would have quietly returned. One
of the new tests exists purely to pin that ordering.

**And we were careful not to break the honest case.** A genuine
thin-evidence refusal still says "insufficient grounding," exactly as
before. That's also a test — the fix must not sweep legitimate refusals
into the outage message, which would be the same mistake in reverse.

### Fix 2 — the scenario label survives

Two separate problems needed two separate fixes:

1. **The removal was too broad.** It now matches whole words only. A
   flagged short term can no longer rewrite longer words that happen to
   contain it.
2. **The rulebook was missing vocabulary.** It now recognises the
   scenario-naming families (`SSP` and `RCP`) as legitimate climate
   terms rather than suspected data sources — including variants like
   `RCP8.5` and `RCP2.6` that aren't individually listed.

**What we deliberately did *not* do.** We did not declare that `RCP8.5`
and `SSP5-8.5` mean the same thing. They're from different generations
of climate science and whether they're comparable is a **scientific
judgement for you to make, not a coding decision.** Our fix only says
"these are scenario names, not dataset names" — which is true regardless
of how the two systems map onto each other.

### Fix 3 — the system can now tell the outside world it's broken

The response now includes the "AI was unreachable" flag, so anything
calling this system — including our own load test — can tell an outage
apart from an honest refusal.

### The proof

We re-ran the identical load test, same 16 questions, same crowding:

| | Before the fixes | After the fixes |
|---|---|---|
| Failures the test could see | **0** | **9**, each correctly named |
| Answers claiming "not enough evidence" | **10** | **0** |
| Average wait | 19.4s | 17.5s (unchanged) |

**Zero false claims about the evidence.** Every refusal is now either a
genuine gap in the data, a question the system is not allowed to answer,
a request for clarification, or an honest "our service failed."

We also checked the fix against the exact sentence that had broken:
the answer that once read `[UNVERIFIED DATASET REMOVED]5-8.5` now reads
`SSP5-8.5`, with `RCP8.5` and `RCP2.6` intact too.

**Seven new automatic tests** were added so none of this can quietly
come back. The full suite is 59 tests, running in about 20 seconds.

### Two honest caveats

**The outage counts aren't comparable between the two runs.** By the
time we re-tested, a full day of testing had used up most of the free
allowance, so outages happen even with one user at a time. What *is*
comparable is the message: it stopped lying.

**Fixing the filter exposed the same blind spot in our own test tool.**
Once outages produced new wording, our load test started counting them
as successful answers — the identical mistake, one level up. We fixed
that too. It's a good illustration of why this class of bug is hard:
every layer has to be taught what failure looks like.

### One thing we confirmed is *not* a bug

The repaired answer still contains one `[UNVERIFIED DATASET REMOVED]`.
We checked the logbook: the removed word was **UKCP09** — the
*previous* generation of UK climate projections.

That is the guard working exactly as intended. UKCP09 is a real
dataset, but it isn't on this system's approved list, so the system is
not authorised to cite it. Deleting a *scenario label* was the bug;
deleting an *unapproved data source* is the whole point.

---

## 10. Was the cleanup done by a different AI model?

A fair question, because the standard advice is to review with a
*newer, stronger* model than the one that built the thing — on the
grounds that fresh eyes catch what the original missed.

**Honest answer: no.**

| Cleanup round | Which model |
|---|---|
| 1 | Claude Opus 5 |
| 2, 3, 4 | **Not written down** — a record-keeping gap |
| 5, 6 | Claude Opus 5 |

So rounds 5 and 6 were the same model reviewing, among other things, its
own earlier review. That's self-review, not the independent audit the
advice describes.

**And some of what we found supports that criticism.** Round 1 wrote a
table claiming the filter safely ignored `RCP8.5`. It didn't — and five
rounds of the same model re-reading its own notes never noticed.

**But round 6 also points to a different conclusion.** Nine problems
turned up not because of a smarter model, but because of a **change of
method**: we ran the system instead of reading it. Same model as round 1.
Switching from reading to running found more in one hour than four
rounds of re-reading had.

So the fair summary is that there are two different levers, and we've
only pulled one:

- **A different model** gives you independent eyes. *Untested here — a
  genuine gap.*
- **A different method** gives you facts instead of predictions. *This
  is what finally worked.*

**The recommendation for next time:** use a genuinely different model,
and point it specifically at the parts that have only ever been *read*
and never *run* — the document search and the rulebook's design. Those
are exactly where our biggest remaining unknowns are (we still can't
measure whether the search finds the right pages), and exactly where
six rounds of the same model's reading has had the least traction.

---

## 11. What about CI/CD?

**What CI/CD means.** **CI** (Continuous Integration) means: every time
someone changes the code, a robot automatically runs all the checks, so
mistakes get caught before they reach anyone. **CD** (Continuous
Deployment) means the robot also *installs* the new version
automatically once the checks pass.

### What exists

There is a CI robot configured (`.github/workflows/ci.yml`). When code
is pushed, it is supposed to:

| Step | What it does | Would it pass today? |
|---|---|---|
| 1. Start a test database | A throwaway copy of the storage system | ✅ Yes |
| 2. Apply database updates | Runs all three upgrade files in order | ✅ Yes — verified by hand this round |
| 3. Code tidiness check (**linter** — a tool that reads code for sloppy patterns without running it) | `ruff` | ✅ Yes — clean |
| 4. Custom safety check | Catches one specific mistake this project made before | ✅ Yes — clean |
| 5. Run the 59 automatic tests | | ✅ Yes |
| 6. Run the 10 hostile "red team" questions | | ✅ Yes — 10 out of 10 |
| 7. Generate fresh answers for quality scoring | Calls the real AI | ⚠️ Would hit the free-tier limit |
| 8. Score answer quality, fail if below 0.80 | | ❌ **No — fails by design** |

### The honest answer: CI has never actually run, and it would fail

**Two separate problems.**

**First, it has never run at all.** The robot needs a password (an
**API key** — a secret code that lets the system use the AI service),
stored in the repository settings. That has never been set up, so any
push fails immediately on the missing password without testing anything.
A one-time settings task, not a coding job.

**Second — and more interesting — even with the password set, CI would
still fail.** Step 8 is a **quality gate**: it demands a score of 0.80
and stops the build if answers score lower. The real scores are 0.778
and 0.473. We checked the script, and it genuinely does stop the build
when a score falls short.

**So the pipeline is designed to stay red until answer quality
improves.** That is the gate doing exactly its job — it should not let
below-standard answers ship.

But it creates a real practical problem worth naming: **a build that is
always red teaches people to ignore it.** Once "CI is failing" is the
normal state, nobody notices when it starts failing for a *new* reason.
The conventional fix is to separate the two kinds of check:

- Things that must *never* break (tests, tidiness, safety) → block the
  build.
- Things you are trying to *improve* (answer quality scores) → record
  them, report the trend, but don't block.

Then a red build always means something new is wrong. **This is a change
we have not made** — it is a recommendation, and it is a judgement call
about how strict you want to be.

### What about the load test in CI?

Deliberately **not** included, for two honest reasons: it needs a fully
running service (not just the code), and on the free tier it would mostly
measure the AI provider's usage limit rather than our system — while
burning the daily allowance the other steps need. A load test belongs on
a schedule against a real deployed environment, not on every code change.

### And CD — automatic deployment?

**There is none, and that is the bigger gap.** There is a recipe for
packaging the app (a **Dockerfile**, which describes how to build a
self-contained bundle), and that bundle has still never been built or
started. Everything in this project has been run by hand. There is also
no **registry** (a shared store where packaged versions live), and
nothing that installs a new version anywhere.

One concrete thing from this round that would bite any future
deployment: **the first request after any restart takes 202 seconds.**
An automatic deployment would need to send one warm-up question before
letting real users in, or the first person after every release waits
three and a half minutes.

---

## 12. The current tests — what they are, in plain language

The cleanup advice says tests must *justify their presence*, and
suggests grouping them into buckets and asking which are slow and which
do not matter. Here is that inventory. **63 tests in total.**

### The fast, genuinely valuable ones — 59 tests, about 5 seconds of actual work

| Group | How many | What it protects | Worth keeping? |
|---|---|---|---|
| **Regression tests** | 19 | Each pins a specific bug that actually shipped, so it cannot silently return. Includes the 7 added today | ✅ The most valuable group — every one has a real incident behind it |
| **Guardrails** | 8 | The safety checks: blocking hostile questions, stripping invented data sources, refusing when evidence is thin | ✅ Yes — this is the product's core promise |
| **Permission tiers** | 6 | That the system refuses to give financial or legal advice and escalates to a human | ✅ Yes |
| **Document search** | 6 | That search behaves correctly, including when it finds nothing | ✅ Yes |
| **Calculation step** | 5 | That the calculator fails safely — reporting timeouts and bad output instead of crashing | ✅ Yes |
| **Rulebook lookups** | 5 | That the approved-data-source rulebook resolves correctly | ✅ Yes |
| **Database layer** | 5 | That connections are set up correctly | 🟡 Thin, but cheap |
| **The custom safety check itself** | 5 | Tests for the tool that checks for one particular past mistake | 🟡 Testing a test-tool. Defensible, low value |

### The slow, low-value ones — 4 tests, 3.5 to 9 minutes

| Group | How many | What it protects | Worth keeping? |
|---|---|---|---|
| **End-to-end "whole system" tests** | 4 | Supposedly that a question travels correctly through the entire system | ❌ **As written, almost nothing** |

**Why these do not justify their presence as written.** Three of the
four only test shortcuts that never reach the AI at all (out-of-scope
questions, blocked questions, and no-data-available questions). The
fourth skips itself in certain conditions, and when it does run it only
checks that two labels exist in the logbook — **it never looks at the
answer.**

The proof: all four passed during the window when 70 of 91 questions
were failing completely. They take up to 9 minutes and cannot tell a
working system from a broken one.

**The fix is not deletion** — covering the whole-system path is the right
idea. It needs one check that fails when the AI was unreachable. That
single line would have caught this round's worst bug automatically.

### The surprise: pruning tests would barely help the speed

The advice suggests a time budget — around 30 seconds — because a slow
test suite slows down every piece of work. We measured where our time
actually goes:

| | Time |
|---|---|
| Running all 59 fast tests | **~5 seconds** |
| Just *loading* the software libraries, before any test runs | **~15 seconds** |
| Whole suite, start to finish | **13–40 seconds** (varies with disk caching) |

**So roughly three-quarters of the time goes on loading libraries, not
running tests.** The AI and maths libraries this project uses are simply
large and slow to load.

**Why this matters:** the obvious advice — "delete low-value tests to go
faster" — would gain almost nothing here, because the tests are not what
is slow. You could delete *every* test and still wait 15 seconds. The
real lever is loading those heavy libraries only when they are actually
needed.

This is a good example of why measuring beats assuming. Had we followed
the advice without checking first, we would have spent effort pruning
tests and watched the suite get barely any faster.

### Honest summary on tests

- ✅ We are **inside** the 30-second budget (13–40s, mostly loading).
- ✅ The regression tests are genuinely good and have grown with every
  bug found.
- ❌ We have still **never done a deliberate test-pruning pass** — the
  one weak group was found by accident while chasing something else.
- ❌ The 4 whole-system tests are the clearest "does not justify its
  presence" case in the project, and are still unfixed.
- 💡 The speed problem is not the tests at all — which we only know
  because we measured instead of assuming.
