# What "Deslopify" Means, and What We Actually Did

This document explains, in plain language, what a "maintenance round"
(nicknamed **deslopify**) is, why we did six of them on this project,
and exactly what was found and fixed each time. No jargon without an
explanation — every technical word is defined in **bold** the first
time it's used.

---

## What is "slop," and what does "deslopify" mean?

When you build something quickly with an AI assistant, it's easy to end
up with small messes: tests that don't really check anything, tools
that are set up but never actually turned on, code left over from a
feature you removed, or small bugs that get patched in a rush without
fixing the real cause underneath. That accumulated mess is informally
called **slop**.

**Deslopify** means pausing new feature work and going back through the
project on purpose, looking for that mess, and cleaning it up — usually
by having a second, independent AI review read the whole codebase with
fresh eyes, since it isn't attached to any of the original shortcuts.

This isn't a one-time thing. Good practice is to do a maintenance round
whenever a lot has changed, before a big release, or whenever a smarter
AI model becomes available — since a stronger model can catch things a
weaker one missed the first time.

---

## Round 1 — the first cleanup (2026-09-14)

A stronger AI model (Opus 5) read the entire project and wrote a report
*before* anything was changed — so a human could review the findings
first, rather than letting the AI change things unsupervised. It found
4 real bugs:

1. **The emergency-stop switch didn't work.** A setting meant to
   instantly pause the whole system only worked if you restarted the
   program — during an actual incident, that's too slow.
2. **Two things running "at the same time" were secretly sharing one
   notepad instead of each having their own.** This caused their
   cost-tracking numbers to overwrite each other instead of adding up
   correctly.
3. **A search filter was silently blocking almost everything** instead
   of narrowing down results the way it was supposed to.
4. **The single most important promise of this project — "the AI
   cannot invent a fake climate dataset name" — wasn't actually being
   enforced.** The check meant to catch a made-up name could, by how it
   was written, never actually catch one.

All four were fixed, and each one got its own permanent automated test
(a **regression test**: a check that runs every time the code changes,
specifically designed so this exact bug can never quietly come back).

---

## Round 2 — fixing the quality-scoring tool (2026-09-21)

The project was supposed to use a real tool called **RAGAS** to
automatically grade how good the AI's answers were. It had been broken
the whole time — it would silently fall back to a much cruder, fake
estimate instead of failing loudly, so nobody could tell it wasn't
working.

Fixing it for real surfaced two more, completely unrelated bugs:

1. **Every single question to the AI was silently getting a blank
   answer.** The AI provider had renamed one of the models being used,
   and the backup model also had no working key. The system was built
   to fail gracefully instead of crashing — which worked exactly as
   designed, but it meant the failure was invisible unless someone went
   and read the logs by hand.
2. **The quality-scoring tool's own settings were too small**,
   cutting off its answers halfway through and reporting a broken
   result instead of a real one.

Once both were fixed, the project got its first ever **real** quality
scores — not fake ones. They came out mediocre (below the target), which
is a genuine, useful finding about answer quality, not a sign that
anything is broken.

---

## Round 3 — the last known gaps (2026-09-21 to 09-22)

This round closed out several items that had been written down as
"still owed" since Round 1:

- **A test that didn't actually test anything got fixed** — and the
  moment it was made to check something real, it immediately caught yet
  another genuine bug: the system could sometimes report the wrong data
  source for a location, because of how its internal rulebook was
  built. Both were fixed together.
- **A code-quality checker (a tool called a linter, which reads your
  code for sloppy patterns without running it) had been configured for
  months but never actually installed or run.** It was finally turned
  on, found 24 real issues, and every one was fixed by hand — not
  blindly auto-fixed — after checking each one was a real problem and
  not a false alarm.
- **A small custom check was written** for one specific mistake this
  project had made before (the "sharing one notepad" bug from Round 1)
  so that if the same *shape* of mistake ever happens again anywhere
  else in the project, it gets caught automatically and instantly,
  instead of waiting for another human review.
- **A security gap was closed:** code the AI writes and runs by itself
  was accidentally able to see the project's private API keys, even
  though it never needed them. Fixed so it no longer can.
- **A mislabeled number was fixed:** a rough estimate was being written
  into permanent records labeled as if it were a precisely measured
  score. It's now honestly flagged as an estimate everywhere that
  record is used, including in the report meant to be shown to a
  regulator.

---

## Round 4 — telling a real breakdown apart from an honest "I don't know" (2026-09-22)

Before this round, two completely different situations looked identical
from the outside: the system correctly saying "I don't have evidence for
that," and the system being **completely broken** — unable to reach the
AI model at all. Both produced an empty answer. That's exactly how the
Round 2 outage went unnoticed for so long.

Fixed by adding an explicit flag that records "both the main AI and the
backup failed," carried all the way through to the permanent record and
into an automatic check that raises an alarm on a *single* occurrence —
not an average, because one silent total breakdown is already one too
many.

---

## Round 5 — restating the business problem, which uncovered a new bug (2026-10-05)

This round changed no code. It started as a writing task: the project's
business problem had been sketched as a story ("imagine a city
planner…") rather than stated plainly, and the person it's actually for
had never been defined. Both are now written down properly, along with
how you'd work out the financial return, in
`docs/business-problem-and-alignment.md`.

Doing that meant re-reading evidence the project had already produced
months earlier — and that's where the surprise was.

**The bug:** the system had been deleting a genuine piece of climate
vocabulary out of its own answers. `RCP8.5` is the label the UK's
official climate reports use for their high-emissions scenario. The
system's internal rulebook only lists the *newer* style of label
(`SSP5-8.5` and friends), so it didn't recognise `RCP8.5` as a real
term, decided it looked like a made-up data source, and replaced it with
a warning notice — in the middle of real answers, about the one country
this project has actually proven.

Nothing fake got through. The safety check was being **too strict**,
not too loose, which is the opposite of the famous bug from Round 1 and
sits in the very same piece of code. But the effect on a reader is
serious: the answer keeps the number ("UK summers warming by up to
5.4°C") and deletes the label saying *under which scenario* — which is
the one detail that makes the number mean anything.

**Why nobody noticed:** the file containing that mangled answer had been
in the project since Round 2 and had been quoted in three different
documents — but only ever for its *scores*. Nobody had read the answer
text those scores were grading. The score said "mediocre quality, tune
the wording." The text said "a safety check is deleting your labels."
Those lead to completely different work.

The bug is written up with three possible fixes and is not yet fixed,
because choosing between them is a scientific judgement about which
emissions scenarios are comparable — an owner's call, not a maintenance
one.

---

## Round 6 — the system was switched on and pushed (2026-10-05)

Every round before this one examined the project by **reading** it — the
code, and the files it had produced earlier. Round 6 did something none
of the others did: started the database, loaded the UK climate reports,
served the system, and then deliberately sent it many questions at once
to see what broke.

A lot broke, and two things broke badly.

**The serious one: when the AI model was unreachable, the system told
users the climate evidence was insufficient.** The AI service this
project uses has a free-tier cap on how much text it can process per
minute. Send two questions at once and that cap is hit. A backup model
is configured but has no access key, so it fails too. At that point
there is no AI at all — and the message the user receives says, in
effect, "the evidence isn't strong enough to answer."

That is a false statement about climate science caused by a billing
limit. **Measured: 70 out of 91 questions.** Every one looked like a
perfectly normal, successful response.

What makes this interesting rather than just bad: the system already
*knew*. It records the difference between "no evidence" and "the AI was
down" in its permanent log, correctly, every time — and its monitoring
alarm spotted all 70 within seconds. The only broken link is the last
one: the part that writes the user's message has no access to that
information. The right fact was in the right place and simply never
reached the person who needed it.

**The second one: the system deleted the scenario the user asked
about.** Asked "what is the heat risk for the UK under SSP5-8.5," it
replied discussing "[UNVERIFIED DATASET REMOVED]5-8.5."

The anti-invention filter decided the three letters `SSP` looked like an
unapproved data source and removed them — and because it removes text by
simple find-and-replace, it also rewrote every longer word containing
those letters, including the scenario name itself. Nothing fake got
through; it is the opposite failure, a guard being too aggressive. But
the effect on a reader is serious, because the scenario label is what
makes a temperature number mean anything.

**Things that worked, verified rather than assumed:** the database and
its upgrades installed themselves correctly; the UK reports produced
exactly 517 searchable pieces, the number three documents had been
quoting; the full pipeline genuinely retrieves real report pages with
page numbers; 52 automated tests pass in under 20 seconds; and all three
monitoring alarms fired correctly on a real incident.

**And one number that was simply wrong in the old docs:** the first
question asked after starting the system takes **202 seconds**, because
two AI models are loaded from disk only when first needed. Later
questions take 2–20 seconds. The docs had said "roughly 35 to 90
seconds," which matched neither.

**The lesson, which is the same one this log keeps relearning one level
up:** reading a system tells you what it is meant to do. The files it
left behind tell you what it did once. Only running it tells you what it
does.

---

## Checked against the four standard deslopify prompts

The advice this practice comes from gives four specific things to ask a
coding agent to clean up. Here is where this project stands against each
of them, checked rather than assumed (2026-10-05):

| # | The prompt | Status here |
|---|---|---|
| 1 | **Prune low-value code and tests** — "tests must justify their presence"; make impossible states unrepresentable | 🟡 Half done, and the missing half now has a concrete target. The *code* side happened across Rounds 1–3: dead code deleted, `evaluation/ragas_eval.py` removed entirely, 24 real linter findings fixed by hand, and `ragas`/`datasets` removed from `requirements.txt` where they contradicted the whole point of the isolated environment. The *test* side has still never been done deliberately — and Round 6 found exactly the kind of thing it would catch: a 9-minute integration suite that passes through a 77% failure rate. See below |
| 2 | **Turn useful standards into fast checks** (lint rules) | ✅ Done, and the strongest item. `ruff` was configured from the start but had never once been installed or run; Round 3 turned it on, found 24 real issues, and added it to CI. Round 3 also added `tools/check_shared_concurrent_state.py`, a custom check for the exact shape of the Round 1 concurrency bug — the project-specific rule the advice asks for, written because `ruff` has no plugin system to host it |
| 3 | **Reassess the implementation** — knowing what we know now, what would we build differently? | 🟡 Partially, three times now. Round 1 was a full read-only audit by a stronger model before any change, which is the right shape. Round 5 asked the broad question and got a concrete bug report rather than an architectural rethink — exactly the experience the original advice describes, for the same reason: a broad question gets you findings, not architecture. **Round 6 found the better method: stop asking and run the thing.** One hour of actually serving traffic produced six defects that five rounds of careful reading had missed. Still no holistic "would we design it this way from scratch" pass |
| 4 | **Revisit agent instructions and skills** — prune what over-steers a newer model | ➖ Genuinely N/A, verified by inspection. There is no `AGENTS.md`, no `CLAUDE.md`, and no skills directory anywhere in this project. Nothing has accumulated because nothing was ever set up. Worth knowing rather than assuming: this was checked, not skipped |

**The test suite has now been timed (2026-10-05), and the numbers make
the case for the advice better than the advice does:**

| Suite | Time | Verdict |
|---|---|---|
| 59 unit tests | **13–40 seconds** across several runs | Inside the 30-second budget at the fast end — but see the measurement below, because the number of tests is barely why |
| 4 integration tests | **3m34s to 9m23s** (varies with how rate-limited the AI service is) | The problem |

The integration suite costs 15x what the entire unit suite costs, and
during this round it was discovered that **it passed while the system
was failing 70 of 91 queries.** Three of its four tests only exercise
paths that never call the AI model, and the fourth checks that two
fields exist in a record without looking at the answer at all.

So this is the clearest possible example of the "tests must justify
their presence" prompt: up to 9 minutes of runtime buying almost no
protection on the path that matters. The fix is not deletion — those
paths deserve coverage — it is adding one assertion that fails when the
system is in outage, which would have caught this round's worst defect
automatically.

**But the speed advice itself turned out not to apply here, and that is
worth knowing.** We measured where the time actually goes:

| | Time |
|---|---|
| Running all 59 fast tests | ~5 seconds |
| Merely *loading* the libraries, before any test runs | ~15 seconds |
| Whole suite | 13–40 seconds |

**About three quarters of the wall-clock is library loading, not
testing.** So "delete low-value tests to go faster" would gain almost
nothing: you could delete every test and still wait 15 seconds. The real
lever is loading the heavy AI and maths libraries only when they are
needed.

Had the advice been applied without measuring first, the effort would
have gone into pruning tests, the suite would have got barely faster,
and the box would have been ticked. The full test-by-test inventory,
with which groups earn their keep, is in
`docs/what-we-did-in-plain-language.md` section 12.

**And the thing that had to be fixed before any of this could be
measured:** the project's development environment was broken. The
`.venv` folder recorded an absolute path to a Python installation under
a different user account (the project folder had been moved at some
point), so the test suite could not be run at all.

That was repaired during this round by repointing `.venv/pyvenv.cfg` at
the current Python installation — same version, 3.12.10, so no packages
needed reinstalling. The original file was kept as
`.venv/pyvenv.cfg.bak`.

It is worth naming as a finding in its own right, because "the tests
cannot be run" outranks every individual slow or useless test, and it
had gone unnoticed through five previous maintenance rounds — all of
which reviewed the code by reading it rather than executing it.
