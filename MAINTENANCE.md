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
| `RCP8.5`, `SSP5-8.5`, `NAO`, `GMST` | ➖ ignored | scenarios and ordinary terms, not dataset claims |

That last row matters as much as the others: an over-eager filter that
shreds legitimate wording is its own kind of broken.

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

### 6. Smaller items

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
