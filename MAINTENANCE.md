# Maintenance Log

Plain-language record of maintenance rounds on this project — what a
maintenance round is, what we found, and what is still outstanding.

---

## What a maintenance round is (and why bother)

When you build something quickly — especially with an AI assistant, and
especially while debugging live — you fix problems one at a time, in the
order they blow up in your face. Each fix is reasonable on its own. But
the fastest fix is often not the *right* fix: it makes the symptom go
away by moving the problem somewhere less visible.

A maintenance round is a deliberate pause to go back and look at the
whole thing with fresh eyes, asking: *which of these fixes papered over
something structural?*

**When to do one:**

- A lot has changed since the last one.
- You just finished a big push, or you're about to ship.
- You pivoted direction.
- A stronger AI model became available — a good excuse to re-examine
  decisions made with less capable help.

**One rule:** a human stays in the loop. The point is to *understand*
what changed, not to hand a codebase to a tool and accept whatever
comes back.

---

## Round 1 — 2026-09-14

**Trigger:** two long build-and-debug sessions had accumulated a lot of
reactive fixes. Reviewed with Claude Opus 5.

**Method:** a read-only review pass over the whole codebase first
(nothing changed), then fixes applied by hand, then a regression test
written for each bug so it cannot silently come back.

### The four bugs we fixed

#### 1. The kill switch didn't actually switch

**What was wrong:** `main.py` copied the `AGENT_PAUSED` setting into a
variable *once, when the program started*. After that, changing the
setting did nothing.

**Why it mattered:** this is the emergency brake. The documented
incident procedure is "set `AGENT_PAUSED=True`" — and following that
procedure would have appeared to do nothing while the system kept
answering questions. It only worked in our earlier demo because we
restarted the server, which hid the bug.

**The fix:** a small function, `is_agent_paused()`, that checks the
setting fresh every single time a request arrives.

#### 2. Two agents were sharing one clipboard

**What was wrong:** the RAG agent and the analysis agent run at the same
time, and both were handed *the same* state object to write their
results into. Imagine two people writing on one sheet of paper
simultaneously.

**Why it mattered:** their cost figures collided. The workaround in the
code took the *larger* of the two numbers, which meant the cheaper
agent's spending vanished from the record — and that number goes into
the audit trail you'd show a regulator.

**The fix:** each agent now gets its own copy to write on, and the two
costs are **added together** instead of one being thrown away.

#### 3. The search filter was quietly excluding everything

**What was wrong:** when searching stored documents, the filter had
three conditions (dataset, scenario, region). Two of them were forgiving
about missing information; the dataset one was strict.

**Why it mattered:** every document we'd loaded was tagged `UKCP18`. So
the moment a question resolved to any *other* dataset, the strict filter
matched zero documents, and the system fell back to "insufficient
grounding." Retrieval wasn't filtering — it was switching itself off.
This is very likely what pushed us into editing the knowledge graph
earlier (see backlog item 1) — we treated the symptom, not the cause.

**The fix:** the dataset condition is now forgiving in the same way the
other two already were. An untagged document is one we know *nothing*
about, not one we know to be irrelevant.

#### 4. The anti-hallucination guarantee was doing nothing

**What was wrong:** this is the headline claim of the whole project —
"structurally cannot hallucinate a dataset name." The check worked like
this: scan the answer for dataset names *from the approved list*, then
verify each one is on the approved list.

Read that twice. It could only ever find names that were already valid,
then confirm they were valid. A made-up name like `CMIP7` was invisible
to it. There was even an unused piece of code sitting in the file — the
approach that *would* have worked, written and then never wired up.

**Why it mattered:** it's the core promise to the customer. It was
decorative.

**The fix:** the check now looks for anything *shaped like* a dataset
name and classifies it:

| Example | Verdict | Why |
|---|---|---|
| `CMIP6`, `UKCP18` | ✅ allowed | on the approved list |
| `CMIP7`, `UKCP09` | ❌ removed | looks like a real one, isn't on the list |
| `SuperClimate9000 dataset` | ❌ removed | presented as a data source, not on the list |
| `CHIRPS` | ❌ removed | a genuine dataset, but not one we're authorised to cite |
| `SSP5-8.5`, `NAO`, `GMST` | ➖ ignored | scenarios and ordinary terms, not dataset claims |
| `RCP8.5` | ⚠️ **intended to be ignored, actually removed** | see the correction below |

That last row matters as much as the others: an over-eager filter that
shreds legitimate wording is its own kind of broken.

> **Correction (2026-10-05).** This table originally listed `RCP8.5`
> alongside `SSP5-8.5` as "ignored." That was the intent, and it is not
> what the code does. `SSP5-8.5` is in `schema.json`'s scenario list, so
> it is recognised as known vocabulary and skipped. `RCP8.5` is not in
> that list — the schema holds only SSP labels — so it falls through to
> the "presented as a source" check, where the phrasing `RCP8.5 data` or
> `RCP8.5 projections` matches and the token is stripped as an
> unverified dataset. Verified by running the real filter, and by the
> stored output in `evaluation/eval_records.json`. Tracked as backlog
> item 7 below. The sentence immediately above this correction turns out
> to have been describing a bug this project already had.

### Turning bugs into tests

Every bug above now has a test in `tests/unit/test_regressions.py`.
Each one records, in its docstring, what actually broke and why the
assertion is worded the way it is — so a future reader doesn't
"simplify" the fix straight back into the bug.

---

## Backlog — known, not yet done

Listed honestly, roughly by importance.

### 1. ~~The knowledge graph was edited to match one laptop~~ — decision made: leave it, documented

To make a Kerala query work, we changed the knowledge graph so Kerala
flood risk points at **ERA5** — because that's the file that happened to
be downloaded. But ERA5 is *historical* data. It has no future emissions
scenarios at all, so the entry `{flood, SSP5-8.5, Kerala, ERA5}` is
scientifically imprecise on its face (the `SSP5-8.5` label on that entry
doesn't mean the returned data reflects that scenario — it's real
historical data, labelled with a scenario tag that doesn't strictly
apply to it).

**Decision (2026-09-21):** keep it as-is rather than building a
substitution-layer fix — ERA5 is real, verified data, and the
alternative (removing Kerala entirely until real scenario data exists)
loses a working, demonstrated capability for a scientific nuance that
doesn't come up unless someone is comparing Kerala directly against a
scenario-modelled region. The mitigation is documentation, not code: the
data status table in `README.md` and `docs/business-problem-and-
alignment.md` both call out that Kerala answers are historical-baseline,
not future-scenario projections. **Not done, and now explicitly
deferred rather than silently dropped:** nothing in the answer text
itself or the audit record currently repeats this caveat live, so a user
who only reads one answer (not the README) has no in-context signal
that Kerala's numbers aren't scenario-projected. If Kerala usage grows,
that's the next real gap to close.

### 2. ~~Generated code runs with your API keys in its environment~~ — fixed 2026-09-22

The analysis agent writes Python and runs it in a subprocess. That
subprocess inherited the parent's environment — including
`GROQ_API_KEY`, `LANGSMITH_API_KEY`, and the database URL with its
password — with nothing stopping generated code from reading them.

**Fixed:** `agents/analysis_agent.py` now builds an explicit minimal
`env=` (`_minimal_subprocess_env()`) from a small allowlist of OS-level
variables (`PATH`, `SystemRoot`, `TEMP`, etc.) and passes it to
`subprocess.run` — no project secrets reach the subprocess at all.
Verified this doesn't break real execution: matplotlib chart generation
(the actual thing the analysis agent produces) was smoke-tested under
the restricted environment and produced a real 29KB PNG in ~20s, same as
under the full environment.

### 3. ~~The faithfulness score isn't a faithfulness score~~ — fixed 2026-09-22

`_estimate_faithfulness()` never reads the answer. It returns one of a
few fixed values based on which pipeline stages produced output. That
number was written to the audit record labelled `faithfulness_score` —
where a regulator would reasonably read it as a measured quantity — and
`export_audit_report()`, the actual regulator-facing export function,
had no way to show otherwise.

**Fixed:** added a `faithfulness_measured` boolean column
(`db/migrations/002_add_faithfulness_measured.sql`, defaults to
`FALSE`), wired through `db/models.py`, `agents/supervisor.py`'s audit
record, and both the write and export paths in
`observability/audit_logger.py`, so `export_audit_report()` now
explicitly tells you whether a given record's faithfulness number is a
real RAGAS measurement or the online proxy — every record today is the
latter, honestly labelled as such. **Note:** this migration needs to be
applied to any already-running database (`docker-compose`'s
`docker-entrypoint-initdb.d` only runs on first volume init, so an
existing local Postgres volume won't pick it up automatically) —
CI now applies all files under `db/migrations/` in order rather than
hardcoding just the first one, which was itself a latent bug this fix
exposed.

### 4. The linter never runs

`pyproject.toml` configures `ruff`, but CI never calls it — so the
config and every `# noqa` comment are decorative. It would have caught
two unused imports sitting in `rag/retriever.py` right now. One CI step
fixes this.

### 5. ~~RAGAS evaluation silently falls back~~ — fixed, see Round 2

### 6. The output filter strips `RCP8.5`, UKCP18's own scenario vocabulary — found 2026-10-05, not yet fixed

> **Superseded in scope by Round 6, finding 1 (same day, after running
> the system).** Everything below is correct but describes only half the
> defect: the filter also flags the bare acronym `SSP`, and because it
> removes text with `str.replace` rather than a word-boundary match, it
> rewrites every longer token containing it — so a question about
> `SSP5-8.5` returns an answer about `[UNVERIFIED DATASET REMOVED]5-8.5`.
> Read Round 6, finding 1 for the full picture; the fix options listed
> at the end of this item still apply, plus the substring fix.

**What is wrong:** `knowledge_graph/schema.json` lists only SSP
scenarios (`SSP1-2.6`, `SSP2-4.5`, `SSP5-8.5`). UKCP18 — the one corpus
this project has actually ingested — is written in the older RCP
vocabulary (`RCP2.6`, `RCP4.5`, `RCP6.0`, `RCP8.5`). Since `RCP8.5`
isn't in the KG vocabulary that `_kg_vocabulary()` builds,
`_extract_candidate_dataset_mentions()` doesn't skip it; its alphabetic
stem `RCP` doesn't match a known dataset stem either, so it reaches
`_is_presented_as_a_source()`, where UKCP18's natural phrasing —
"the RCP8.5 data", "RCP8.5 projections" — matches
`{token}\s+(?:dataset|data|projections|...)`. It is then verified
against the KG, fails, and every occurrence is replaced with
`[UNVERIFIED DATASET REMOVED]`.

**Why it matters:** it is the inverse of bug #4 above, in the same
function. Nothing hallucinated gets through — the filter is too strict,
not too loose — but it deletes the emissions-scenario label that makes a
retrieved number mean anything, in answers about the only region this
project is proven for. The business problem is "answers they can check
against a source" (see `docs/business-problem-and-alignment.md`), and
this strips the source's own vocabulary out of the answer. It is also a
plausible partial cause of the 0.473 answer relevancy score.

**Evidence:** reproduced directly against the real filter, and visible
in the stored `evaluation/eval_records.json` `uk_fairness` record, which
contains "projections for [UNVERIFIED DATASET REMOVED] (and RCP2.6,
RCP4.5, RCP6.0)". Note `RCP2.6`/`RCP4.5`/`RCP6.0` survived in that
sentence only because they didn't happen to appear in citation phrasing
— they are stripped the moment they do.

**Not fixed, and the fix is a judgement call, not a one-liner.** The
options are not equivalent:

- Add the RCP labels to `schema.json`'s scenario list. Smallest change,
  but it asserts RCP scenarios are valid query scenarios for the KG,
  which affects traversal and `scenario_adjacency`, not just this
  filter.
- Add a separate "known non-dataset vocabulary" set that the filter
  skips without making the terms valid KG scenarios. Narrower and
  probably correct, but it is a new concept in the schema.
- Add an explicit SSP↔RCP equivalence mapping. The most useful of the
  three, because it would also let a question asked in SSP terms match
  UKCP18 text written in RCP terms — which is a retrieval problem this
  project has independently (see the relevancy diagnosis in
  `docs/business-problem-and-alignment.md`) — but it is a scientific
  judgement about which pathways are comparable, and that is an owner
  decision, not a maintenance fix.

Whichever is chosen needs a regression test in the same shape as the
existing `test_scenarios_and_acronyms_are_not_dataset_citations`.

### 7. Smaller items

- Four `TODO` comments in `config.py` are already done; one
  (`ALERT_OWNER`) is genuinely still open but looks identical.
- `.env.example` is missing about a dozen settings that exist in
  `config.py`, so "read one file to see the whole envelope" only
  half-works.
- `test_parent_region_fallback` asserts a condition that passes either
  way, so it doesn't test what its name says.
- The integration test skips itself exactly when backlog item 1 bites.
- Docstrings in `rag_agent.py` and `kg_agent.py` still say they run "in
  PARALLEL" with each other; the supervisor deliberately runs the
  knowledge graph agent first (RAG needs its output).
- `scenario_adjacency` in `schema.json` references `SSP3-7.0`, which
  isn't in the scenario list — so that fallback path is unreachable
  through normal use.

---

## Round 2 — 2026-09-21

### RAGAS fixed for real, and it found two more bugs on the way

The old `evaluation/ragas_eval.py` (backlog item 5) tried to import the
real `ragas` library in the same venv as production and silently fell
back to a crude proxy when that failed — which it always did, since
`ragas`'s dependencies conflict with `langgraph`/`litellm`. Fix: `ragas`
now lives in its own venv (`.venv-ragas`, pinned in
`requirements-ragas.txt`), with a two-phase flow —
`evaluation/generate_eval_records.py` (main venv, real pipeline) writes
records, `evaluation/score_eval_records.py` (isolated venv) scores them
with a genuine LLM judge built on the project's existing Groq/LiteLLM
setup. `evaluation/ragas_eval.py` itself has been deleted. CI now runs
this as a separate `ragas-score` job.

Getting there surfaced two real, unrelated bugs, both now fixed:

1. **Every LLM call in the entire pipeline was silently failing.**
   Groq renamed the default model (`qwen/qwen3.6-27b` → `qwen/qwen3.8-27b`)
   sometime after this project was last fully exercised, and the
   fallback model (OpenRouter) has no API key configured. The
   crash-prevention fix from Round 1 (`call_llm` returning `("", 0.0)`
   on a fallback failure instead of raising) was doing its job of not
   crashing — but it meant every query was quietly returning a blank
   answer, with no visible error unless you went and read the logs by
   hand. Fixed by updating `config.py`'s model defaults. **The missing
   alerting this gap left behind — no way to distinguish "both models
   failed" from a normal "insufficient grounding" refusal — is now fixed
   too, see Round 4 below.**
2. **The RAGAS judge's default `max_tokens` (1024) was too small** for
   faithfulness's claim-extraction JSON against real multi-chunk
   contexts, truncating mid-generation and silently scoring as `nan`
   rather than a real failure. Fixed by raising it to 4096 in
   `score_eval_records.py`.

The real scores that came out the other end (0.778 faithfulness, 0.473
answer relevancy, both below the 0.80 bar; context precision is
currently meaningless — see README) are the first genuine, non-proxy
quality numbers this project has ever produced. They're mediocre, not
broken — a real finding, not a bug in the measurement.

---

## Round 3 — 2026-09-21 (same day, continued)

### Turning the recurring bug into a fast check — done, correcting an earlier wrong claim

Backlog item "turn recurring test patterns into lint rules" is now done,
though not the way `docs/maintenance-round-1-opus5.md` originally
described it. That doc claimed "ruff supports some custom rules" — that
was wrong; ruff has no plugin system for project-specific rules (it's a
single compiled Rust binary with a fixed rule set). The actual fix:
`tools/check_shared_concurrent_state.py`, a standalone AST-based script
that catches the exact shape of bug #2 above (the same mutable object
handed to two or more concurrently-scheduled tasks without a copy) —
anywhere it recurs in the project, not just the one spot already fixed.
It runs as its own CI step, same spirit as a linter (fast, no test
execution) even though it isn't literally one. Covered by
`tests/unit/test_check_shared_concurrent_state.py`.

Also, fixing the vacuous `test_parent_region_fallback` test (the other
open backlog item) immediately surfaced a real, previously-unknown bug:
the knowledge graph's region->dataset edges weren't scenario-specific,
so a region reachable under multiple scenarios with different datasets
could resolve to the wrong one. Fixed in `knowledge_graph/builder.py`
and `knowledge_graph/query.py`, with a build-time validation added so
`schema.json` can't be authored ambiguously again without an immediate
error. This is exactly the pattern this whole log keeps returning to:
tightening a test that only *looked* like it checked something found a
real bug, on the first try.

### Ruff itself had never actually run, either

Separately from the custom check above: `pyproject.toml` had configured
`ruff` since the start, but it had never once been installed or run —
not a CI gap, a "the tool doesn't exist in this environment" gap. Fixed:
installed it, ran it for the first time, and fixed all 24 real findings
by hand rather than blind `--fix` (confirmed each one was real before
touching it — e.g. the `B023` closure warnings in `rag/chunker.py`
turned out to be false positives, verified by checking the closure is
never stored past the loop iteration it's defined in). Also found and
removed `ragas`/`datasets` sitting in `requirements.txt`, contradicting
the entire point of the `.venv-ragas` isolation from Round 2. `ruff
check .` now runs as its own CI step.

---

## Round 4 — 2026-09-22

### Operational reliability: telling a real outage apart from a correct refusal

The single biggest gap Lan Chu's metrics framework pointed at (see
`docs/engineering-practices-review.md`) was operational reliability —
error-rate tracking on failed LLM calls. This is exactly the category
that would have caught the Round 2 outage (Groq silently renaming a
model, breaking every LLM call) automatically instead of it being found
by hand.

**Fixed:** `call_llm()` now returns a third value, `llm_unavailable`,
set only when both the primary and fallback model calls fail. This is
threaded through every call site (`supervisor.py`, `kg_agent.py`,
`analysis_agent.py`), onto `ClimateRiskState`, into the audit record,
through a new DB column (`db/migrations/003_add_llm_unavailable.sql`),
and into a new `check_llm_outage()` check in
`evaluation/online_monitor.py` that alerts on even a single occurrence
in a 15-minute window — deliberately not averaged like the faithfulness
drift check, since one silent total outage is already one too many.
Also fixed `_estimate_faithfulness()` to score 0.0 on an LLM outage
even when real evidence was retrieved, instead of a misleadingly
positive "evidence was present" score for an answer that's actually
empty. `online_monitor.py` also had no runnable entrypoint at all
despite `README.md` claiming it "runs every hour" — added one
(`run_all_checks()` + a `__main__` guard); actually scheduling it
hourly is still a deployment step, not something this file can do
alone.

**An honest note on doing this work:** while adding the regression test
for this fix, an edit briefly mis-diagnosed a real, correct assertion
in an existing test (`test_scenarios_and_acronyms_are_not_dataset_citations`)
as leftover dangling cruft and deleted it. Checking `git log -p` on the
file before concluding it was actually junk caught the mistake and it
was restored. Recorded here because the entire point of this log is not
hiding mistakes just because they were caught before shipping.

---

## Round 5 — 2026-10-05

### Documentation round: the business problem got stated properly, and reading the stored evidence found a new bug

**Trigger:** the business problem had been written down as a persona
sketch ("imagine a city planner…") rather than a statement, and the
user it serves had never been defined. Both are now fixed in
`docs/business-problem-and-alignment.md`: the problem is "make climate
information usable by people who aren't climate specialists, with
answers they can check against a source," the user is "people who need
sourced climate information for planning but lack specialist support,"
and the problem is sourced to Williams et al. rather than assumed. That
document also now carries an ROI model with every input labelled
measured-or-supplied-by-the-business, which the project previously had
nowhere at all.

**The ROI model changed as a consequence, not as a separate edit.** The
old pitch was cost substitution — "consultant quality answers at the
cost of asking a question." The problem statement doesn't support that:
Williams et al.'s first finding is that there *aren't enough*
specialists, which is a supply constraint, not a price one. You can't
substitute a cost nobody was paying. So the model is now capacity
created rather than cost avoided, measured in decisions that got a
sourced climate input instead of currency per query saved, with
traceability written as a separate 0-or-1 term because an untraceable
answer is unusable for this user rather than merely worse. Worked
through in `docs/business-problem-and-alignment.md` Part 3. This also
reorders the open-defect list: the RCP8.5 bug outranks the
below-threshold quality scores, because it attacks the traceability
term rather than reducing the quality one.

**No code changed in this round.** One correction and one new finding
came out of it, both from reading evidence this project had already
produced and never re-read:

1. **A claim in this log was wrong.** Round 1's filter-behaviour table
   listed `RCP8.5` as "ignored." It isn't — see the correction inline
   above, and backlog item 6.
2. **A new bug, found in `evaluation/eval_records.json`.** The stored UK
   answer contains `[UNVERIFIED DATASET REMOVED]` twice, where `RCP8.5`
   should be. That file had been sitting in the repo since Round 2,
   quoted for its *scores* in three documents, without anyone reading
   the answer text it scored. Reproduced against the live filter to
   confirm the mechanism before writing it up. Details in backlog
   item 6.

**Also checked, since this round was a review pass:** where the project
stands against the four standard deslopify prompts (prune code/tests,
turn standards into fast checks, reassess the implementation, revisit
agent instructions). Result: fast checks are the strongest item, test
pruning has still never been done deliberately, and the fourth prompt is
genuinely N/A — verified by inspection that there is no `AGENTS.md`,
`CLAUDE.md` or skills directory anywhere in this project, so nothing has
accumulated to prune. Table in
`docs/deslopify-in-plain-language.md`. One concrete new gap came out of
it: the test suite had never been timed, and at the time could not be —
the project `.venv` recorded an absolute interpreter path under a
different user account, so the suite would not run at all. **Fixed in
Round 6** by repointing `.venv/pyvenv.cfg` at the current 3.12.10
install (original kept as `.venv/pyvenv.cfg.bak`); the suite now runs in
19.2s.

**The lesson worth keeping:** the eval records were treated as a number
(0.778 / 0.473) rather than as output. The number said "mediocre
relevancy, needs prompt tuning." The text said "a guardrail is deleting
the scenario label out of your answers." Those lead to completely
different work, and only one of them is right. A score tells you
something is wrong; only the artefact tells you what.

---

## Round 6 — 2026-10-05

### The system was actually run, under load, for the first time — and the headline guardrail claim broke

**Trigger:** every previous round reasoned about this system from its
code and its stored artefacts. Nothing had been stood up end to end and
pushed. Docker was started, Postgres was brought up on a fresh volume,
the UKCP18 corpus was ingested, the API was served, and a load test was
run against it. This round is what that produced.

**What stood up correctly, verified rather than assumed:**

- `docker compose up postgres` boots pgvector and applies **all three**
  migrations on a fresh volume — `audit_log` came up with both
  `faithfulness_measured` and `llm_unavailable` present. The caveat in
  backlog item 3 (that `docker-entrypoint-initdb.d` only runs on first
  volume init) is correct as written.
- Ingestion produced **exactly 517 chunks**, the number three documents
  have been quoting: Land report 241, Marine 154, Overview 92, starters
  guide 30. No page needed OCR fallback.
- The pipeline runs end to end. A UK heat question traversed five KG
  nodes (`hazard:heat → variable:temperature → scenario:SSP5-8.5 →
  region:UK → dataset:UKCP18`), retrieved 5 real UKCP18 pages, and wrote
  a complete audit record.
- `52` unit tests pass in **13–19s** (measured across three runs). The "45 tests" figure in the older
  docs was stale. Getting there required repairing the dev environment
  first: `.venv/pyvenv.cfg` pointed at a Python install under a
  different user account (the project folder had been moved), so the
  suite would not run at all. Repointed at the current 3.12.10 install —
  same version, so no reinstall — with the original kept as
  `.venv/pyvenv.cfg.bak`. **Five rounds of review never caught this,
  because none of them tried to execute anything.**
- `ruff check .` is clean and the custom shared-state check passes.
- **All three monitors fired correctly on real incident data** — see
  below. Regulatory question Q3 is now verified under an actual
  incident, not a simulated one.

### Finding 1 — the output filter destroys the scenario label by substring

Backlog item 6 understated this badly. The real defect is worse than
"RCP8.5 gets stripped."

`_extract_candidate_dataset_mentions()` flags the bare acronym **`SSP`**
— it is not in the KG vocabulary (only the full labels `SSP1-2.6`,
`SSP2-4.5`, `SSP5-8.5` are), its stem matches no known dataset, and
phrasing like "SSP projections" trips the
"presented as a source" check. It then fails KG verification, and
`verify_and_filter_datasets()` removes it with
`filtered_text.replace(dataset, "[UNVERIFIED DATASET REMOVED]")`.

`str.replace` is substring-based. So removing `SSP` rewrites **every
longer token containing it**. Verified live, from the real answer to
"What is the heat risk for the UK under SSP5-8.5?":

> "I cannot provide the specific heat risk for the UK under
> **[UNVERIFIED DATASET REMOVED]5-8.5** … the question asks for
> **[UNVERIFIED DATASET REMOVED]5-8.5** … while the text mentions that
> **[UNVERIFIED DATASET REMOVED]s** were used for CMIP6"

The scenario the user literally asked about is destroyed in the answer.
Reproduced in isolation too: the input "SSP projections were used for
CMIP6. The question asks for SSP5-8.5, and SSPs differ from RCP8.5"
comes back with all three `SSP` occurrences mangled while `CMIP6`
and `RCP8.5` survive.

So there are two defects stacked, and they need separate fixes:

1. **Vocabulary** — bare `SSP` and `RCP` are not recognised as
   non-dataset terms (backlog item 6 as originally written).
2. **Blast radius** — a flagged token is removed by substring across the
   whole answer, so any short acronym takes valid longer tokens with it.
   This one is independent of climate vocabulary and would bite any
   short token that ever gets flagged. Fixing it means replacing on word
   boundaries (`re.sub` with `\b`), not `str.replace`.

### Finding 2 — a rate-limited outage is reported to the user as "insufficient grounding"

This is the most serious finding of the round, and the load test is what
exposed it.

Under concurrency, Groq's free tier rejects calls on **input tokens per
minute (ITPM): limit 7,000** — the API log carries 89 `RateLimitError`s,
each naming that limit. The fallback model is OpenRouter, which has no
key configured, so it raises `AuthenticationError` (178 of them). Both
models having failed, `call_llm` returns `llm_unavailable=True`,
`_estimate_faithfulness()` correctly scores 0.0, and the output filter
returns the standard below-threshold message:

> "Insufficient grounding to answer confidently. The retrieved evidence
> does not meet this system's faithfulness threshold…"

**Of 91 audit rows written during this round, 70 had
`llm_unavailable = TRUE` — and all 70 returned that message.** Average
faithfulness across the window: 0.213.

That message is a false statement about the data. The evidence may have
been retrieved perfectly well; the model that would have used it never
ran. A planner reading it would conclude the climate record is too thin
to answer — when the truth is "our LLM provider rate-limited us." For a
system whose entire pitch is answers you can trace to a source, telling
the user the source was inadequate when it wasn't is worse than an error
page.

Round 4 added the machinery to tell these two states apart, and that
machinery works. The gap is that nothing uses it on the user-facing
path: `apply_output_filter()` has no knowledge of `llm_unavailable`, so
it cannot pick a different message.

### Finding 3 — the API never exposes `llm_unavailable`

Related but separate. `main.py`'s `/query` response returns
`groundedness_score`, `coverage_gap`, `litellm_cost_usd` and ten other
fields, but **not** `llm_unavailable`. The flag reaches the audit record
and the database; it never reaches the caller.

So no client — including the load test written this round — can
distinguish an outage from a refusal. The load test's own report said
"0 failures" at every concurrency level while 70 queries were in total
LLM outage, because every one of them was an HTTP 200 carrying a
plausible refusal. A load test that checked only status codes would have
certified this system as perfectly healthy.

### Finding 4 — the analysis agent always fails on the UK path, and the failure leaks into the answer

The KG resolves UK heat questions to `UKCP18`, which is a PDF corpus
with no NetCDF files. So `run_analysis_agent` fails every time with
"No local NetCDF file configured for dataset 'UKCP18'" — not
occasionally, but on every UK query, which is the only region with
ingested data.

Worse, `_combine_results()` puts the failed result into the prompt
verbatim (`f"Quantitative analysis: {state.analysis_results}"`), and the
model uses it as evidence against itself. From the live answer:

> "**Missing Quantitative Analysis:** The metadata indicates
> `Quantitative analysis: {'success': False}` due to a lack of local
> NetCDF file configuration, confirming that the specific numerical heat
> projections required to calculate a 'heat risk' were not successfully
> retrieved or processed."

An internal configuration failure is being surfaced to the user as a
reason the climate evidence is insufficient. Two things are wrong: a
failed tool result should not enter the grounding context at all, and
the UK path should not be routing to an analysis agent that cannot
serve it.

### Finding 5 — the documented way to run the monitor does not work

`README.md` says to run `python evaluation/online_monitor.py`. That
fails with `ModuleNotFoundError: No module named 'config'`: the script
never puts the project root on `sys.path`. `rag/ingest.py` does exactly
this, with a comment explaining why. `online_monitor.py` needs the same
four lines, or the README needs to stop documenting a command that
cannot work.

Once run correctly, it behaves exactly as designed — all three checks
fired on the real data:

- LLM outage: 70 occurrences in 15 minutes → alert
- Faithfulness drift: 0.213 over 91 queries → alert
- Per-region segments: Global 0.000 (15 queries), Kerala 0.076 (17), UK
  0.306 (59) → alert on all three

### Finding 6 — cold start is 202 seconds

The first request after a server restart took **202 seconds**. Every
subsequent request took 2–20s. The embedder and the cross-encoder
reranker are both lazily loaded on first use (`_get_model()`,
`_get_reranker()`), and the `lifespan` startup hook only configures
LangSmith. So the first user after every deploy waits three and a half
minutes.

This also corrects a number carried in the docs: latency was described
as "~35–90 seconds observed informally." Measured, it is ~2–20s warm and
202s cold. Neither figure matched.

### Finding 7 — the SQL pre-filter does not narrow anything

`README.md` described the pre-filter as narrowing "~10,000 chunks to
~200 candidates" for "a ~50x smaller search space per query." Measured
against the real corpus, it does neither:

| Query resolves to | Rows surviving the pre-filter |
|---|---|
| UKCP18 + SSP5-8.5 + UK/Global | **517 of 517** — narrows nothing |
| CMIP6 + SSP5-8.5 + Mumbai/South_Asia | **0 of 517** — excludes everything |
| ERA5 + SSP5-8.5 + Kerala/South_Asia | **0 of 517** — excludes everything |

The cause is visible in the stored metadata: `ingest_directory()` tags
every chunk with `dataset='UKCP18'` and leaves `scenario` and `region`
as `NULL`. Since the scenario and region clauses tolerate `NULL`, they
match everything; the dataset clause does not tolerate a *mismatch*, so
it is all-or-nothing. The filter is a binary gate on the dataset tag,
not a 50x narrowing — and it is why Kerala and Mumbai questions retrieve
zero chunks. That outcome is still an honest refusal, but the mechanism
is not the one the documentation described.

The `~50x` and `~10,000` figures were architectural aspirations stated
as measurements. They have been corrected in `README.md`.

### Finding 8 — the integration suite cannot detect any of this, and costs 9 minutes

The integration tests passed — 4 of 4 — during the same window in which
70 queries were in total LLM outage. That is not luck; it is structural:

- Three of the four tests exercise only short-circuit paths
  (`out_of_scope`, `tier_1`, `coverage_gap`). None of those reach an LLM
  call at all, so no LLM failure can affect them.
- The fourth, `test_valid_query_produces_audit_record`, is the only one
  that runs the real pipeline. It `pytest.skip()`s when routing doesn't
  reach a terminal branch, then asserts exactly two things: that
  `query_id` equals `trace_id`, and that the string
  `"faithfulness_score"` is a key in the audit record. It asserts
  nothing about the answer, so it passes identically whether the system
  produced a good grounded answer or nothing at all.

So the suite takes **3m34s to 9m23s** (measured twice; the runtime is
dominated by LLM rate-limit backoff, so it varies with how contended the
provider is) and cannot distinguish a
healthy system from one that is failing three quarters of its queries.
The existing backlog note ("the integration test skips itself exactly
when backlog item 1 bites") was pointing at the right test and
understating the problem — skipping is the lesser issue; asserting
nothing about the answer is the real one.

This is the concrete version of the test-pruning work that has been
listed as not-started since Round 1. The fix isn't deletion — these
paths are worth covering — it is adding an assertion that fails when
`llm_unavailable` is true, so the suite can tell an outage from a
refusal the way the monitor already can.

### Finding 9 — LangSmith recorded the entire outage as 100% successful

This is the finding that best explains why the other eight went
unnoticed, and it was only found by querying LangSmith's API directly
after the incident.

Tracing is genuinely wired up and genuinely working: the APAC endpoint
is configured, the key authenticates, the `climate-risk-agent` project
exists, and it received traces during this round's run. Queried
afterwards, it held 100 spans:

| Span name | Count |
|---|---|
| `supervisor` | 41 |
| `LangGraph` | 20 |
| `kg_agent` | 15 |
| `analysis_agent` | 12 |
| `rag_agent` | 12 |

**All 100 have `status = "success"`. Zero have the error field set.**
Every one of them was recorded during the window in which 70 of 91
queries were failing completely.

Two causes, both structural:

1. **There are no LLM spans at all.** Every one of the 100 runs has
   `run_type = "chain"`. Not one is `run_type = "llm"`. `call_llm()` in
   `agents/__init__.py` carries no `@traceable`, and litellm's own
   LangSmith callbacks (`litellm.success_callback` /
   `failure_callback`) are not configured. So the 89 `RateLimitError`s
   and 178 `AuthenticationError`s — the actual failures — have no span
   to appear in. The traces cannot show a failure in a call they never
   recorded.
2. **The agent spans succeed by design.** `call_llm` deliberately
   returns `("", 0.0, True)` rather than raising, so the pipeline never
   crashes. That is the right production behaviour, but it means each
   agent function returns normally, and LangSmith marks the span
   successful. The `llm_unavailable=True` flag is in the returned data,
   not in the span status.

Only four functions in the project carry `@traceable`, all of them agent
entry points. Not traced: `call_llm` (where the outage happened),
`rag/retriever.py`'s four-stage retrieval (where retrieval quality would
be visible), and every guardrail in `guardrails/` — including
`apply_output_filter`, where the `SSP` destruction happens.

So the three places this project's real defects live are precisely the
three places with no instrumentation.

**The practical proof:** diagnosing this round's incident required the
`audit_log` table and the server's stderr. LangSmith contributed
nothing, and if it had been the only observability in place, the
honest conclusion from the dashboard would have been "100 runs, all
green." A tracing setup that reports success through a 77% failure rate
is worse than none, because it actively provides false assurance.

What to fix, in order: wire litellm's LangSmith callbacks so LLM calls
and their failures become real `llm` spans with token counts; add
`@traceable` to `retrieve()` and the guardrail entry points; and set
span status from `llm_unavailable` so a trace fails when the system
fails.

### Fixes applied, same day, verified under load

Findings 1, 2 and 3 are **fixed and verified against live traffic**. The
rest remain open and are listed in
`docs/business-problem-and-alignment.md` Part 5.

**Fix for finding 2 (outage reported as insufficient evidence).**
`apply_output_filter()` takes a new `llm_unavailable` argument and checks
it *before* the groundedness threshold — ordering matters, because an
outage always scores 0.0 faithfulness, so the outage branch would be
unreachable in the other order. On outage it returns a message that says
the model service failed and explicitly states this is **not** a
judgement about the climate evidence. `agents/supervisor.py` passes
`state.llm_unavailable` through. The genuine thin-evidence refusal keeps
its original wording.

**Fix for finding 1 (scenario labels destroyed).** Two independent
changes, because it was two bugs:

- *Blast radius:* removal now uses `re.sub` with `\b` word boundaries
  instead of `str.replace`. A flagged short token can no longer rewrite
  longer tokens that merely contain it.
- *Vocabulary:* `_kg_vocabulary()` now also includes the bare
  scenario-family acronyms, derived from `schema.json`'s scenario list
  (so `SSP` comes from `SSP5-8.5` automatically, and a new scenario
  needs no code change), plus `RCP`, which is absent from the schema but
  is the vocabulary UKCP18's own reports use. A new `_scenario_stems()`
  check then exempts *unlisted* members of a known family — `RCP8.5`,
  `RCP2.6`, `SSP3-7.0` — which the bare acronym alone did not cover.

  This deliberately does **not** assert that any RCP pathway equals any
  SSP pathway. That equivalence is a scientific judgement for the
  project owner and remains open (backlog item 6's third option). The
  fix only says "these are scenario labels, not dataset claims," which
  is true however the pathways map.

**Fix for finding 3.** `/query` now returns `llm_unavailable`.

**Fix for finding 5.** `evaluation/online_monitor.py` now bootstraps the
project root onto `sys.path`, matching `rag/ingest.py`,
`red_team_suite.py`, `generate_eval_records.py` and
`score_eval_records.py`, all four of which already did. A survey of the
runnable scripts found it was the only one missing it, which is why the
command `README.md` had documented since the module was written had
never once worked. Verified: all three checks now run from the
documented command. (`evaluation/load_test.py` and
`tools/check_shared_concurrent_state.py` also lack the bootstrap and
correctly so — neither imports a project module.)

### CI/CD, assessed

Not a new finding so much as a conclusion the round makes unavoidable.
**CI has never completed a run, and configuring the missing secret will
not make it pass.**

Steps 1–6 of `.github/workflows/ci.yml` would now pass: Postgres with
all three migrations, `ruff` clean, the shared-state check clean, 59
unit tests, and 10/10 red team — every one of those verified by hand
this round. Step 7 (`generate_eval_records.py`) calls the real LLM and
would hit the free-tier token limit. Step 8 (`score_eval_records.py`)
**exits 1 whenever any metric is below `RAGAS_THRESHOLD` (0.80)**, and
the real scores are 0.778 / 0.473 / 0.0 — confirmed by reading the exit
path, not assumed.

So the pipeline is designed to stay red until answer quality improves.
That is the gate working correctly, and it is also a practical problem:
a permanently-red build trains everyone to ignore it, and the next
genuine regression arrives into a signal nobody reads. The conventional
split is worth considering — hard-fail on tests, lint and safety;
record-and-trend the quality metrics without blocking — so that red
always means something new. **Not changed**, because how strict to be
about shipping below-threshold quality is an owner decision, not a
maintenance one.

**CD does not exist.** The `Dockerfile` has still never been built or
run; every execution in this project, including this round's, was by
hand. There is no registry and nothing that deploys. One concrete
constraint this round adds for whenever that is built: the 202-second
cold start means any deploy needs a warm-up request before traffic, or
the first user after every release waits three and a half minutes.

**The load test is deliberately not in CI**: it needs a running service
rather than just the code, and on the free tier it would mostly measure
the provider's rate limiter while consuming the token budget the eval
steps need. It belongs on a schedule against a deployed environment.

### The test suite, inventoried and timed

The "tests must justify their presence" prompt, finally answered with
measurements rather than an estimate. 63 tests: 59 unit, 4 integration.

| Group | Count | Verdict |
|---|---|---|
| `test_regressions.py` | 19 | Strongest group — each pins a bug that actually shipped |
| `test_guardrails.py` | 8 | Core product promise |
| `test_tier_authority.py` | 6 | Core governance |
| `test_rag_retriever.py` | 6 | Retrieval behaviour incl. empty results |
| `test_analysis_agent.py` | 5 | Safe-failure paths |
| `test_kg_query.py` | 5 | Rulebook resolution |
| `test_db_retriever.py` | 5 | Thin but cheap |
| `test_check_shared_concurrent_state.py` | 5 | Tests for a test-tool; defensible, low value |
| `tests/integration/` | 4 | **The one group that does not justify itself** — see finding 8 |

**And a measurement that inverts the obvious advice.** Per-test
durations total **~5s**; `--collect-only` (imports, no execution) takes
**~15s**; the whole suite runs in **13–40s** depending on OS file
caching. So roughly three quarters of the wall-clock is spent importing
torch/sentence-transformers/litellm, not running tests.

The implication matters: pruning tests would buy almost nothing here.
Deleting every test would still leave ~15s. The real lever is deferring
the heavy imports. Had the "delete low-value tests to go faster" advice
been applied without measuring first, the effort would have produced a
barely-faster suite and a false sense of having addressed it. The suite
is already inside the 30-second budget the advice recommends — for
reasons that have nothing to do with the number of tests.

**Seven regression tests** added to `tests/unit/test_regressions.py`,
including the three that pin behaviour most likely to be refactored back
into the bug: that a real grounding failure still says "insufficient
grounding", that the outage check precedes the threshold check, and that
an invented dataset name (`SuperClimate9000`) is still stripped — both
fixes loosen the filter, so the original Round 1 guarantee needed
pinning. Suite: 59 passing, 19.3s. `ruff` clean.

**Verified against the exact text that failed.** The live answer that
had come back as `[UNVERIFIED DATASET REMOVED]5-8.5` now passes through
with `SSP5-8.5`, `RCP8.5`, `RCP2.6` and `SSPs` all intact; only
`UKCP18` and `CMIP6` are flagged, and both verify true.

**Verified under load — the result that matters.** Same 16-request
workload, before and after:

| | Before | After |
|---|---|---|
| Failures the load test could see (c=16) | **0** | **9**, all named `llm_unavailable_both_models_failed` |
| Answers claiming "insufficient grounding" (c=16) | **10** | **0** |
| p50 / p95 latency (c=16) | 19.43s / 23.06s | 17.47s / 23.16s — unchanged |

Every refusal is now either a genuine coverage gap, a Tier-1 block, a
clarification request, or an honestly-labelled outage. **Nothing lies
about the evidence any more.** A real outage response now reads:

> "No answer was generated: the language model service was unavailable
> (both the primary and fallback models failed). This is a system
> failure on our side, NOT a judgement about the climate evidence…"

Two honest caveats on those numbers. The absolute outage counts are not
comparable between runs — by the time the post-fix test ran, a day of
testing had consumed most of the free tier's token budget, so outages
occur even at concurrency 1. What *is* comparable is the message. And
fixing the filter exposed the same blind spot inside the load test
itself: it classified the new outage prose as "answered" until a check
was added, which is the identical failure mode one level up.

**One behaviour confirmed as correct, not a bug.** The post-fix UK
answer still contains one `[UNVERIFIED DATASET REMOVED]`. The audit
record shows the stripped token was `UKCP09` — the previous generation
of UK projections. That is the guardrail working exactly as designed:
`UKCP09` is a real dataset but is not on the approved list, and Round
1's own table lists it as correctly removed. Scenario labels being
stripped was the bug; unapproved dataset names being stripped is the
feature.

### Was the deslopping done by a different model? No — and that is worth recording

The practice this log follows says to audit with a *newer, stronger*
model than the one that built the thing, on the grounds that it catches
what the previous one missed. This project has never actually tested
that premise:

| Round | Model |
|---|---|
| 1 | Claude Opus 5 |
| 2, 3, 4 | **Not recorded** — a traceability gap in this log |
| 5, 6 | Claude Opus 5 |

So Rounds 5 and 6 are Opus 5 reviewing, among other things, Opus 5's own
earlier review. That is self-review, not the cross-model audit the
practice describes, and some of what Round 6 found supports the
criticism — Round 1 wrote a table claiming `RCP8.5` was ignored by the
filter when it was not, and five rounds of the same model's reading never
caught it.

But Round 6 is also evidence for a different conclusion than "use a
better model." Nine findings came not from more capability but from a
**change of method**: running the system instead of reading it. The
model was identical to Round 1's. Switching from reading to executing
produced more in an hour than four rounds of re-reading.

Both are worth doing, and they find different things. A genuinely
different model is the untested option here, and remains the honest
recommendation for Round 7 — ideally pointed at the parts Rounds 1–6
only ever read: the retrieval stack and the knowledge-graph design.

### What this round says about the previous five

Rounds 1–5 were conducted by reading code and artefacts. They were not
wrong — every bug they found was real — but five rounds of careful
reading did not surface findings 2, 3, 4, 6 or 7, and understated
finding 1. All of them appeared within an hour of actually running the
thing under load.

The pattern is the same one this log keeps recording, one level up:
reading a system tells you what it is supposed to do, and the stored
evidence tells you what it did once. Only running it tells you what it
does. A load test was listed as a gap for five rounds; the reason to
close it was never the latency numbers.

---

## Verdict from the review

> The architecture is genuinely sound — the layering is coherent,
> docstrings are thorough and mostly honest about their own limitations,
> config centralisation is real, and error handling is applied
> consistently rather than ad hoc. No full refactor is warranted.

The four fixed bugs shared one trait worth remembering: **each was a
place where the fastest available fix moved the problem into a layer
where it stopped being visible.** That's the specific thing a
maintenance round is good at catching, and it's why the review pass was
read-only first — so nothing got "fixed" before it was understood.
