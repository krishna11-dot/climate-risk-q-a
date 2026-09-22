# What "Deslopify" Means, and What We Actually Did

This document explains, in plain language, what a "maintenance round"
(nicknamed **deslopify**) is, why we did three of them on this project,
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

## What's still left, honestly

Two things are genuinely not done yet, and there's no benefit in
pretending otherwise:

- **Nobody has gone through every single automated test one at a time**
  asking "does this actually check something real?" Every fix so far
  came from finding a bad test by accident while doing something else.
- **Nobody has stepped back and asked, "if we built this whole project
  again today, knowing what we know now, would we design it the same
  way?"** That's a deliberate, bigger exercise, separate from fixing
  individual bugs, and it hasn't been done.

Neither is urgent. Both are reasonable to leave for a future round.

---

## A note on a second, different source discussed alongside this one

A second piece of material was discussed alongside this document, about
a completely different topic: a workflow for **starting a brand-new**
project with an AI coding agent (talking through the idea, picking a
tech stack, planning architecture — all before writing code). That's
not what a maintenance round is for, since this project already exists
and isn't being started from scratch. If a comparison against that
material's advice would be useful too, that's a separate, explicit check
worth doing on its own — just say so.
