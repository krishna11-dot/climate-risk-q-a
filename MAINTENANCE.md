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

### 1. The knowledge graph was edited to match one laptop *(needs a decision)*

To make a Kerala query work, we changed the knowledge graph so Kerala
flood risk points at **ERA5** — because that's the file that happened to
be downloaded. But ERA5 is *historical* data. It has no future emissions
scenarios at all, so the entry `{flood, SSP5-8.5, Kerala, ERA5}` is
scientifically wrong on its face.

The deeper problem: the knowledge graph is supposed to hold *scientific
truth*, and it's what the anti-hallucination check trusts. It now also
holds "what's on this developer's disk," and you can't tell the two
apart by looking.

**Suggested direction:** put the correct science back in the graph, and
add a separate substitution layer (e.g. `data_availability.json`) saying
"the ideal dataset isn't available locally, here's what was used
instead" — recorded visibly in the audit trail rather than hidden inside
the graph.

### 2. Generated code runs with your API keys in its environment

The analysis agent writes Python and runs it in a subprocess. That
subprocess inherits the parent's environment — including `GROQ_API_KEY`,
`LANGSMITH_API_KEY`, and the database URL with its password.

There's a timeout, so it can't hang forever. But nothing stops it
reading those keys. **Cheap fix:** pass an explicit minimal `env=` to
`subprocess.run`. Also worth softening the docstring, which currently
claims protection against "malicious" code that isn't actually there.

### 3. The faithfulness score isn't a faithfulness score

`_estimate_faithfulness()` never reads the answer. It returns one of a
few fixed values based on which pipeline stages produced output. That
number is then written to the audit record labelled `faithfulness_score`
— where a regulator would reasonably read it as a measured quantity.

**Options:** rename it honestly (`evidence_coverage_proxy`) and add
`faithfulness_measured: false` to the record, or finish wiring the real
RAGAS evaluation (see item 5).

### 4. The linter never runs

`pyproject.toml` configures `ruff`, but CI never calls it — so the
config and every `# noqa` comment are decorative. It would have caught
two unused imports sitting in `rag/retriever.py` right now. One CI step
fixes this.

### 5. RAGAS evaluation silently falls back

`evaluation/ragas_eval.py` tries the real RAGAS library, fails, and
quietly substitutes the crude internal proxy — so the scores reported
aren't what they claim to be. Related to item 3.

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
