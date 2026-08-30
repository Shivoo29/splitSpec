# Where things stand — pick up here

Written 2026-08-30 evening. All twelve modules are built and verified; what remains
is evidence and submission material.

## What just happened (read this first)

`difflib` does not emit the "no newline at end of file" marker. **Every source file
in `fixtures/eventpulse/app/` lacks a trailing newline** (11 of 13), so whenever the
fixer rewrote a file, the `-`/`+` pair for its final line ran together on one
physical line, `_parse_diff` matched neither, and `apply_patch` **silently deleted
that line**.

That fired on **21 of 22 runs** in the first sweep. A correct patch lost a `return`
statement, the endpoint failed response validation, and the gold suite recorded a
failure the model never caused. The `ResponseValidationError ... input: None`
signature in old artifacts is this bug, every time.

Fixed in `sandbox._unified`, with a mutation-checked regression test in
`tests/test_sandbox.py`. Proof it mattered, same model and same patch:

| issue-10-splitspec | gold | decision |
|---|---|---|
| before the fix | FAIL 1/5 | ACCEPT (scored as a false accept) |
| after the fix | **PASS 5/5** | ACCEPT (a correct fix, correctly accepted) |

**Every metric in the README predates the fix and is invalid.** The sweep is being
re-run; do not report any number until it finishes.

## Tomorrow, in order

1. **Check the sweep.** `tail sweep3.log`, and
   `grep -l '"ok": false' artifacts/issue-*/result.json | wc -l` for failures.
   Provider read timeouts are common — re-run the identical command, completed
   pairs skip and failed pairs retry. Two or three that never complete is a
   limitation to report, not something to fight.

2. **Recompute the metrics** and update the README results table. The block that
   prints recall / validity / mutation / medians with their denominators is in the
   chat history; `splitspec/metrics.py` computes the same things.

3. **Reproducibility (15 pts — the biggest gap).** A judge cannot currently reach
   the main result: it needs three provider keys, hours of runtime, and
   non-deterministic models. Fix by committing the artifacts (`result.json`,
   `review_packet.md`, `trajectory.md`, `verifier_test.py`,
   `mutation_results.json`) and adding a reporter that recomputes the table from
   them with no credentials:
   `python -m splitspec.report --from artifacts/ --output evaluation-results.json`
   `metrics.py` already does the computation; it needs a CLI that loads RunResult
   off disk. ~40 minutes, converts the weakest row into a strong one.

4. **Improvement changelog** (`docs/PROJECT.md`, Evidence column is empty and is
   what gets graded). The strongest entries:
   - contract → issue-11 returns `confidence: low`, run escalates instead of
     patching a non-bug
   - validity gate → the issue-07 test it *rejected* (`asyncio.gather` on one event
     loop serialises ASGI requests, so there was no race to catch)
   - mutation → bracketed at both ends: gold kills nearly all, a trivial
     `assert True` kills none
   - budget accounting → issue-07 went `budget`/visible FAIL to `finished`/visible
     PASS; 5,478 tokens generated versus 257,165 billed
   - **the diff fix above** — an iteration where the measurement itself was wrong

5. **Trajectories** (deliverable 4):
   `.venv/bin/python scripts/render_trajectory.py artifacts/issue-01-splitspec ...`
   Two or three representative ones, not all 24.

6. **Video** (5 min): problem → baseline → one real execution → comparison →
   changelog → the change that mattered most. The best 30 seconds is the dashboard
   on a shallow-fix case: green visible beside red gold.

## Decided against

- **A GitHub bot.** No rubric row rewards deployment, and it makes reproducibility
  *worse* — a judge cannot run it without credentials, which Ground Rule 08 forbids
  shipping. Mention it under "not built / next steps" with the reasoning.
- **Chasing a positive recall** by swapping in a larger verifier. One shot, hours of
  quota. A negative result with strong instrumentation is the better submission.

## The change most likely to improve the actual result

A passing verifier test should **never upgrade a verdict** — only a failing one
carries signal. Both false accepts came from `REVIEW REQUIRED` → `ACCEPT`. Absence
of a caught bug is not evidence of correctness. Ten lines in `reporting.decide`,
and it belongs in the changelog as an evidence-driven iteration even if only
reasoned about.

## Claims discipline

`docs/PROJECT.md` §17 has the checklist. Ground Rule 09 requires every claim to
connect to submitted evidence. Do not say the verifier "catches shallow fixes"
unless the new sweep shows it. What is defensible: it generates valid,
mutation-killing tests independently of the fixer, and the validity gate rejects
toothless ones automatically.
