# Maintenance Round 1 (Opus 5) — What We Actually Did vs. the Maintenance Checklist

This document exists because the general write-up (`MAINTENANCE.md` at
the project root) explains *what broke and why*, but doesn't map our
work against a specific maintenance-round checklist you'd seen
elsewhere. This one does that mapping, honestly — including the parts
we skipped.

No jargon left unexplained. If a term appears in **bold** the first
time, it's defined right there.

---

## First: yes, the checklist talks about lint rules and human-in-the-loop

You asked to confirm this. It does, in two separate places:

1. **Human-in-the-loop** — even if you automate maintenance rounds,
   "these things typically still need the human in the loop to pay
   attention to how things are being fixed and updated." Translation:
   don't just let the AI change things and walk away — someone should
   read the diff and understand *why*.

2. **Lint rules** — the advice is: "detect shaky patterns in your
   specific codebase and encode them as custom rules," and separately,
   "if you keep catching the same mistake in tests, encode it as a lint
   rule instead — lint runs in milliseconds, tests run in seconds, same
   protection, faster feedback."

A **linter** is a tool that reads your code without running it and
flags things that look wrong or sloppy — missing imports, unused
variables, inconsistent style. **Ruff** is the specific linter this
project uses (it's already configured in `pyproject.toml`). A **custom
lint rule** means teaching the linter to flag a mistake *specific to
your project* — not a generic Python mistake, but "this codebase keeps
making this exact error, catch it automatically from now on."

---

## The checklist, item by item — what we did and didn't do

### ✅ DONE: "When a smarter model drops, audit your whole project"

We did this. Opus 5 read the entire codebase (everything except the
`.venv` folder, which is just downloaded libraries, not our code) and
produced a written report *before* changing anything. That report found
15 issues, four of which were real bugs (not style complaints — things
that would actually behave wrong in production).

**Why this order matters:** the human-in-the-loop point above is
exactly why we did read-first-then-fix instead of "AI fixes everything
automatically." I read the report, decided which fixes to accept, and
you approved before Opus 5 touched a single file.

### ✅ DONE (partially): "What decisions in this codebase are now stale? What would we build differently?"

Opus 5 flagged one specific stale decision clearly: the knowledge graph
(**the file that says which climate datasets are valid for which
region/hazard/scenario combination** — it's the thing that makes it
*impossible* for the AI to invent a fake dataset name) had been edited
to match whatever file happened to be sitting on this laptop, rather
than to match scientific reality. That's flagged in the backlog, not yet
fixed — it's your call to make, not mine, because it's a *design*
decision, not a bug.

We did **not** do a full "what would we build differently, knowing what
we know now" pass across the *entire* architecture. We reviewed the
specific areas Opus 5 flagged as suspicious (the parts of the code that
had been patched repeatedly during live debugging), not a from-scratch
rethink of the whole system.

### ✅ DONE: fix real bugs found during the audit

Four bugs, explained in plain language in `MAINTENANCE.md`:

1. The emergency-stop switch (**kill switch** — a setting that's meant
   to instantly pause the whole system, e.g. during an incident) didn't
   actually work while the program was running; you had to restart it.
2. Two parts of the system that run "at the same time" (**in
   parallel**) were accidentally sharing one shared notepad instead of
   each having their own, so their cost-tracking numbers overwrote each
   other.
3. A search filter meant to narrow down which documents to search was
   accidentally excluding *everything* for most questions.
4. The single most important promise of this whole project — "the AI
   cannot invent a fake climate dataset name" — was not actually being
   enforced. The check that was supposed to catch invented names could,
   by its own construction, never catch one.

### ✅ DONE: "Turn recurring mistakes into tests"

Every one of the four bugs above now has a matching automated test in
`tests/unit/test_regressions.py`. A **regression test** is a test
written specifically so that if this exact bug ever creeps back in
(e.g. someone "simplifies" the fix without understanding why it's there)
the test fails immediately and says so, instead of the bug silently
shipping again.

### ❌ NOT DONE: "Turn repeated test patterns into lint rules"

The specific advice here: once you notice you keep writing the *same
kind* of test to catch the *same kind* of mistake, that's a sign the
mistake should be caught by the linter instead — because a linter
checks your code in milliseconds every time you save, while a test
suite takes seconds to minutes to run.

We didn't do this. Concretely, here's what a custom lint rule *would*
look like for this project, and why we haven't written one yet:

- One of the four bugs (the shared-notepad problem, #2 above) happened
  because two pieces of code were handed the *same* mutable object
  instead of each getting their own copy. A custom lint rule could flag
  "passing the same object into two things that run concurrently"
  automatically, project-wide — catching the *next* instance of this
  mistake before it ships, not just the one we found.
- Ruff (the linter this project uses) supports some custom rules, but
  writing one from scratch is real work, and we haven't scoped it yet.
  This is an honest gap, not something quietly skipped.

**Backlog item, not yet started.**

### ❌ NOT DONE: "Delete useless tests"

The advice: as a project grows with AI help, the test suite accumulates
junk — tests for features you removed, or tests with good-sounding
names that don't actually check anything real. Ask a smarter model to
audit the *existing* test suite and delete dead weight, because faster
tests mean faster feedback every time you make a change.

We did not do this. We only **added** 10 new tests. Nobody has gone
back through the original ~35 tests asking "does this test still check
something true, or is it checking nothing?" Opus 5's review *did*
independently notice one test that has this exact problem —
`test_parent_region_fallback` in `tests/unit/test_kg_query.py` currently
passes no matter what the code does, because of how its condition is
written — but fixing it wasn't part of this round's scope.

**Backlog item, not yet started.**

### ❌ NOT DONE: "Update AGENTS.md — smarter models need less instruction, not more"

**AGENTS.md** (or `CLAUDE.md`) is a file some projects keep that gives
the AI assistant standing instructions about how to work on that
specific codebase — coding conventions, things to always/never do,
context about the project's history. The idea: those files tend to
accumulate rules that were written to compensate for an *older, weaker*
model's mistakes. When a stronger model arrives, some of those rules are
no longer needed and just add clutter — so periodically prune them.

This project doesn't currently have an `AGENTS.md` or `CLAUDE.md` file
at all, so there was nothing to prune. If you want one going forward
(to give me standing instructions across future sessions, e.g. "always
run the red team suite after touching guardrails/"), that would be a
new thing to create, not a cleanup of an existing one.

**Not applicable yet — no such file exists.**

---

## The trade-off being described here, and why we're only documenting it for now

Lint rules vs. tests is a genuine trade-off, not "lint rules are
strictly better." It's worth spelling out both sides plainly, because
that's *why* we're choosing to write this down now and act on it later,
rather than doing it immediately.

**What a test can catch that a lint rule can't:** a test actually *runs*
the code — it opens a real (or fake) database connection, calls a real
function, checks the real output. Bug #4 from this round (the fake
anti-hallucination check) could only be caught by a test, because the
mistake was in what the code *produced*, not in how it was *written*. A
linter reads code without running it, so it has no way to know that
`verify_dataset_in_kg()` always returns `True` by construction — that
fact only shows up when you actually call it.

**What a lint rule can catch that a test can't, practically:** a lint
rule runs automatically, on every save, in a fraction of a second, on
every line of the whole project — including code nobody has written a
test for yet. Bug #2 (two things running "at the same time" sharing one
shared notepad instead of each getting a copy) is a *pattern* — "handing
the same mutable object to two things that run concurrently" — that
could recur in a completely different part of the codebase tomorrow,
and a test only protects the one spot we already found and fixed. A
lint rule protects everywhere, forever, instantly.

**The actual trade-off, then, is cost vs. reach:**

| | Test | Lint rule |
|---|---|---|
| Catches | This specific bug, in this specific spot | The *shape* of the mistake, anywhere in the project |
| Speed | Seconds to minutes | Milliseconds |
| Effort to write | Usually straightforward — describe one broken scenario | Harder — you're teaching a tool to recognise a *pattern*, which needs to be precise enough to catch real problems without flagging correct code as wrong |
| Risk if done badly | A test that doesn't actually test anything (this already happened once in this project — see `test_parent_region_fallback`) | A rule that misfires on legitimate code, which trains people to ignore linter warnings entirely |

**Why we're just documenting this and not doing it right now:** writing
a *good* custom lint rule takes real, careful effort — getting the
pattern-matching precise enough that it doesn't cry wolf. That's not a
five-minute follow-on to today's bug fixes; it's its own piece of work
that deserves its own focused attempt, not a rushed add-on at the tail
end of a maintenance round. Recording the reasoning now means the
decision of *when* to invest that effort is made deliberately later,
instead of the idea just being forgotten.

## One-paragraph honest summary

Of the checklist above, we did the "big" items — full-project audit by
a stronger model, fixing the real bugs it found, writing regression
tests, and documenting the reasoning — with a human (you) approving
before any change landed. We did **not** do the two "hygiene" items:
turning the fixed mistakes into fast-running lint rules, and auditing
the *existing* test suite for dead weight. Those are real, scoped,
not-yet-started backlog items, not things quietly skipped and forgotten
— they're written down here specifically so they don't get lost.

## What's left

| Checklist item | Status |
|---|---|
| Audit whole project with the stronger model | ✅ Done |
| Fix bugs the audit finds | ✅ Done (4 bugs) |
| Turn each fixed bug into a regression test | ✅ Done (10 tests) |
| Reassess stale architecture decisions | 🟡 Partially — one flagged, not resolved (knowledge graph vs. local files) |
| Turn recurring test patterns into lint rules | ❌ Not started |
| Delete useless/dead tests | ❌ Not started |
| Prune over-prescriptive AGENTS.md rules | ➖ N/A — no such file exists yet |
