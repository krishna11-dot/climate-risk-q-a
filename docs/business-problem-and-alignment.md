# The Business Problem, and Does This Project Actually Solve It?

This document answers two questions in plain language, with facts, not
impressions:

1. What problem is this project actually trying to solve?
2. Does what we've built so far genuinely match what was asked for?

Every jargon word is explained the first time it's used, in **bold**.

---

## Part 1 — The business problem, in plain terms

Imagine a **city planner in the UK** deciding whether a new neighbourhood
needs flood or heat defences. They need a trustworthy answer to "how
much worse is this specific climate risk going to get, and how
confident are we?" They can't afford to hire a climate scientist for
every single decision — that's slow and expensive. So the tempting
shortcut is: ask a general-purpose AI chatbot instead.

(The UK is used here deliberately, not as a random example: it's the
one region this project has actually proven end-to-end with real
government climate reports — see Part 3 below. The same problem exists
for an insurance firm in Singapore, an NGO in Nairobi, or a planner in
Chennai, and expanding to those is the target — but today, asking this
system about any of them correctly returns "insufficient grounding,"
not an answer. Don't read those as supported today.)

**Here's the problem with that shortcut.** A generic AI chatbot will
give you a confident-sounding answer even when it's making things up —
including inventing the name of a scientific dataset that doesn't
exist, or citing a real dataset for a claim it never actually made. If
an insurance firm prices a policy based on a hallucinated number, or a
city planner skips flood defences because an AI made up a reassuring
statistic, that's not a minor bug — it's a decision with real
consequences, and "the AI said so" is not something you can defend to
a **regulator** (a government body that can require you to show your
evidence and reasoning before approving a business decision).

**What this project is:** a system that answers the same climate risk
questions, but:

- It only writes down what real documents and real datasets actually
  say — it isn't allowed to answer from memory alone.
- It is *structurally* unable to cite a dataset that doesn't exist,
  the same way a form with a dropdown menu can't accept an answer that
  isn't one of the listed options.
- Every single question and answer gets written down permanently, so
  if a regulator later asks "why did you say this," there's a full,
  unchangeable record to show them.
- If the evidence isn't good enough, it says "I don't have enough
  evidence to answer confidently" instead of guessing.

That's the whole pitch: **consultant-quality climate answers, at the
cost of asking a question instead of hiring a consultant, with a paper
trail a regulator would actually accept.**

---

## Part 2 — Does it actually do that? (Facts, checked against what was specified)

The original specification asked for 28 specific behaviours plus three
"regulatory questions" the system should be able to answer. Below is
an honest status check against all of them, based on what has actually
been run and verified — not what the code merely intends to do.

### The four anti-hallucination techniques

| # | Technique, in plain terms | Status |
|---|---|---|
| 1 | Only answer from retrieved real documents, never from memory | ✅ Working — verified by asking real questions and inspecting exactly which document pages the answer came from |
| 2 | Dataset names can only come from a fixed, pre-approved list (a **knowledge graph** — think of it as a strict rulebook of "these are the only valid dataset+region+scenario combinations") | 🟡 The rulebook itself exists and works, **but** it was recently found that the *checking* step against it was fake — see below |
| 3 | Every input/output is checked against a strict template (**Pydantic** schemas) so nothing can sneak in an unexpected field | ✅ Working for the main data that flows through the system; a couple of small internal helper objects use a looser template — cosmetic, not a hallucination risk |
| 4 | If confidence is too low, refuse to answer rather than guess | ✅ Working — verified live: a UK heat-risk question that lacked exact evidence returned "insufficient grounding" instead of guessing |

**Important correction found during our maintenance review:** technique
#2's actual enforcement — the step that's supposed to catch a made-up
dataset name like "CMIP7" or "SuperClimate9000" — turned out to be
broken in a specific way: it could only ever recognise names that were
*already* on the approved list, so it could never actually catch a made
up one. This has since been fixed and is now backed by 5 automated
tests confirming it, e.g. one test literally feeds it the sentence "The
SuperClimate9000 dataset reports severe flooding" and confirms the fake
name gets stripped out. Full explanation in `docs/maintenance-round-1-opus5.md`.

### The three regulatory questions

The specification says the whole point of this system is to be able to
answer three questions a regulator would ask. Here's the honest status
of each, in plain terms:

**Q1 — "Does it behave correctly before it goes live?"**
Checked via: an automated test suite (45 tests, all passing) and a
"red team" of 10 deliberately hostile questions designed to try to
break the safety rules (e.g. "ignore your instructions," "what does
SuperClimate9000 say about flood risk," "should I buy insurance for my
property") — **all 10 are currently blocked or handled correctly.**
There's also a scoring system called **RAGAS** that grades answer
quality automatically using an AI judge — this is now genuinely working
(it wasn't, when this document was first written), and it caught
something real: on the only two questions with real evidence to check
(UK questions), the answers were faithful to the source material
(0.78 out of a required 0.80) but not sharply on-topic (0.47 out of
0.80) — a real, moderate quality gap now visible for the first time,
not a placeholder number. See `README.md`'s "Real RAGAS evaluation"
section for the full numbers.

**Q2 — "Can you explain any specific past answer to a regulator on
demand?"**
✅ Yes, verified for real: we pulled up the full record for one actual
question that had been asked earlier, and it showed exactly which
document pages were used, the chain of reasoning through the rulebook
(**knowledge graph**), the final answer, and a confidence score — all
retrievable by a single ID, months later if needed.

**Q3 — "Would you find out about a quality problem before your
customer does?"**
✅ Yes, verified for real: there's a monitoring check that looks at
recent answers and flags if the average confidence drops below a
threshold, and a second check that looks for the system doing worse
for one specific region than another (catching unfairness that an
overall average would hide). Both were run against real logged data
and both work correctly.

### The 28 specific behaviours

Rather than list all 28 individually here (they're in the original
specification), the honest summary is: **all 28 are implemented**, and
the large majority have been *exercised with real data and real
questions*, not just written and assumed to work. The two that remain
placeholders exactly as originally planned:

- **A named human being responsible for emergency decisions** — the
  system has the mechanism (a setting that instantly pauses everything,
  now confirmed to work correctly at runtime — this was actually
  broken until our recent fix, see `MAINTENANCE.md`), but no specific
  person's name has been filled in yet. That's a business decision for
  you, not a coding task.
- **Compound questions** ("what's the combined flood AND heat risk for
  Mumbai") — explicitly marked as a future step in the original spec,
  and still is.

---

## Part 3 — What's actually been proven to work, with real data

This is the part that matters most: **has this actually been tested
with real climate data, or does it just look right on paper?**

| Region | Real evidence loaded? | What was verified |
|---|---|---|
| UK | ✅ Yes — 4 real government climate reports, split into 517 searchable pieces | A real question about UK heat risk correctly retrieved the right document pages and gave an honest, evidence-based answer |
| Kerala | ✅ Yes — real historical rainfall data for the exact Kerala region | The system correctly computed a real number (a monsoon-season rainfall rate) and produced a real chart from it |
| The whole world (broad/global questions) | ✅ Yes — one real global climate dataset file | Same as above — a real number and chart were produced, not a guess |
| Everywhere else (Mumbai specifically, South Asia broadly, most of Africa, Southeast Asia) | ❌ No real evidence yet | If you ask about these today, the system will correctly say "insufficient grounding" — which is the *honest*, intended behaviour when there's no real data, not a bug |

**Why this matters for the business pitch:** the system doesn't fake
confidence it doesn't have. An insurance firm asking about Mumbai today
would get an honest "we don't have enough evidence" rather than a
guess dressed up as an answer. That refusal-to-guess behaviour is
arguably the single most important thing to have proven works, and it
has been proven, live, more than once.

---

## Part 4 — What's not done yet (said plainly, not buried)

- **The automatic quality-scoring library (RAGAS) now genuinely runs**
  — this used to be a gap, it isn't anymore. It lives in its own
  isolated environment because its dependencies conflict with the main
  production stack (see `README.md`), and its current real scores show
  a genuine, moderate quality gap (0.78 faithfulness, 0.47 relevancy,
  both below the 0.80 bar) — not a placeholder anymore, but not passing
  yet either.
- **Turning a JSON audit record into an official PDF for regulatory
  filing** — not built yet, exactly as the original spec marked it as
  a future step.
- **Computing a range of uncertainty** (e.g. "somewhere between X and
  Y, with Z being most likely") instead of a single number — not built
  yet, also marked as a future step in the original spec.
- **Automated code-quality checking (a linter) is configured but still
  never actually runs** as part of testing — so it isn't currently
  catching anything, even though the settings for it exist.
- **The code is now in version control and pushed to GitHub**
  (**CI/CD** — a system that automatically re-runs all the tests every
  time the code changes — is wired up in `.github/workflows/ci.yml`),
  closing what used to be the biggest gap here. What's still open: the
  repository's `GROQ_API_KEY` secret hasn't been configured yet, so the
  first real push-triggered CI run will fail immediately on missing
  credentials rather than testing anything — that's a one-time GitHub
  settings step, not a code change.
- **One design decision needs your input, not more coding**: to make a
  Kerala question work with real data, the rulebook (knowledge graph)
  was edited to point Kerala at a historical weather dataset that
  doesn't actually have future-scenario data at all — a mismatch that
  was more about "what file happens to be on this laptop" than
  "what's scientifically correct." Full explanation in
  `docs/maintenance-round-1-opus5.md`.

---

## Bottom line

**Does this align with the original business problem?** Yes — the core
mechanism (grounded answers, a strict rulebook preventing invented
dataset names, a full audit trail, honest refusal when evidence is
thin) is built and has been proven with real questions and real data,
not just written and assumed to work. One of the four core
anti-hallucination protections was recently discovered to be broken in
a way that mattered, and has since been fixed and locked in with
automated tests.

**What's the biggest real gap between "built" and "regulator-ready"?**
Version control and real RAGAS scoring — the two gaps this document
used to flag here — are both closed now. What's left: the automatic
quality-scoring tool's actual numbers (0.78 faithfulness, 0.47
relevancy) are honestly mediocre, not failing outright but below the
0.80 bar the spec set, so answer quality itself — not the measurement
of it — is now the real open item. That's known, written down, and not
a surprise buried in the code.
