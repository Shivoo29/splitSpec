# SplitSpec

**Independent verification for AI-generated bug fixes.**

> The agent that writes the fix never sees the test that grades the fix.

SplitSpec does not merge, deploy, or approve anything. Its output is a review packet for a
human maintainer.

---

## Who has this problem

A maintainer reviewing a patch produced by a coding agent, on a repository with a normal test
suite and no curated hidden tests.

**The bottleneck is who gets to decide what "done" means.** In the usual workflow the agent
that writes the patch is also the thing that decides the patch is finished - it stops when the
visible tests go green. A shallow fix that satisfies the visible suite without fixing the
behaviour is therefore indistinguishable, at review time, from a correct one. Both arrive
green.

The maintainer's only real defence is to read the patch and imagine the cases the test suite
does not cover. That does not scale, it degrades with reviewer fatigue, and it is precisely the
work a reviewer is least able to do on unfamiliar code.

**Why it is worth solving:** the volume of agent-authored patches is rising faster than review
capacity. A reviewer who cannot tell "fixed" from "looks fixed" becomes either a rubber stamp
or a bottleneck. Neither is acceptable.

## How it works

Four stages with an enforced information boundary between them:

| Stage | Sees | Never sees |
|---|---|---|
| **Contract builder** | The issue text, a file listing | The patch, any test |
| **Fixer** | The contract, the pre-patch repo, the visible tests | The verifier's test, the gold tests |
| **Verifier** | The contract, the pre-patch repo | The patch, the fixer's workspace, the gold tests |
| **Judge** | The patch, all three suites | - calls no model, infers nothing |

The boundary is **structural, not prompted**. The fixer and verifier run in separate
materialised workspaces; each asserts at entry that the other's artifacts are unreachable and
raises if they are not. The verifier's test is hashed and frozen before any patch is judged,
then re-hashed before it is allowed to grade. Gold tests are mounted read-only into a single
container invocation no agent ever touches.

A generated test must pass a **validity gate** before it may grade anything: it has to compile,
run, and *fail on the original buggy code*. A test that passes on the bug would never have
caught a shallow fix, so it is recorded as invalid with its reason rather than silently
counted.

## Results

Measured from real runs in `artifacts/` - Docker sandbox, `--network none`, real models. No figure
below is simulated.

**Models:** contract `openai/gpt-oss-120b` (Groq) · fixer `devstral-2512` (Mistral) · verifier
`gemini-3.1-flash-lite` (Google). Fixer and verifier are different models on different providers.

**Test suite:** 175 unit tests + 17 Docker end-to-end tests pass, 1 skipped.

**Oracle validation.** The gold suites are checked in both directions across all 12 cases, with
zero errors - they fail on every seeded bug and pass on the clean fixture. Without both halves, a
gold suite cannot distinguish a fix from a non-fix and every metric built on it is meaningless.

| | gold on buggy code | gold on clean code |
|---|---|---|
| all 12 cases | **fails** (11 seeded bugs) / passes (issue-11, no bug) | **passes, 12/12** |

**Sweep, 12 cases × 2 modes.** 18 of 24 pairs completed; 6 failed on provider read timeouts on
free-tier endpoints and are excluded. Every rate carries its denominator.

| case | baseline | gold | SplitSpec | gold | verifier |
|---|---|---|---|---|---|
| issue-02 | REVIEW REQUIRED | pass | **ACCEPT** | pass | pass |
| issue-03 | REVIEW REQUIRED | pass | **ACCEPT** | pass | pass |
| issue-04 | REVIEW REQUIRED | pass | **ACCEPT** | pass | pass |
| issue-05 | REVIEW REQUIRED | **fail** | ACCEPT | **fail** | pass |
| issue-06 | REVIEW REQUIRED | pass | **ACCEPT** | pass | pass |
| issue-08 | REVIEW REQUIRED | pass | **ACCEPT** | pass | pass |
| issue-09 | timeout | - | ESCALATE | pass | - |
| issue-10 | REVIEW REQUIRED | pass | **ACCEPT** | pass | pass |
| issue-11 | timeout | - | ESCALATE | pass | - |
| issue-12 | REVIEW REQUIRED | pass | **ACCEPT** | pass | pass |

### Primary outcome: reviewer effort

Success for a maintainer is how many patches they must read by hand.

| Metric | Baseline | SplitSpec | Change |
|---|---|---|---|
| Correct patches auto-cleared | 0 / 9 | **7 / 9** | +7 |
| False rejections | 0 | **0** | - |
| Broken patches cleared | 0 | 1 | +1 |
| **Human reviews required** | **9** | **2** | **−78%** |
| Median runtime per issue | 264 s | 391 s | +127 s |
| Model cost | not measured | not measured | - |

The baseline cannot clear anything: with no independent oracle, every patch returns
REVIEW REQUIRED - including the seven that were correct. SplitSpec clears seven of them with no
false rejections, and escalates two low-confidence cases. The cost is roughly two minutes of
machine time per patch.

### Secondary metrics, and the one that failed

| Metric | Value | Denominator |
|---|---|---|
| Generated test validity rate | 8 / 10 | tests that reached the gate |
| Mutation score (pooled) | 24 / 40 | scored mutants |
| **False-fix detection recall** | **0 / 1** | shallow fixes with a verifier verdict |

**The verifier missed the one shallow fix it was given.** On issue-05 (an IDOR case) the patch
passed the visible suite, failed the gold suite, and the verifier test *passed* - turning a
cautious REVIEW REQUIRED into a confident ACCEPT. One case is not a rate, and the honest reading is
that the oracle-strength question is unresolved here, not answered.

Published work predicts exactly this failure: 80.2% of agent-authored test patches carry weak or no
oracle signal, and strong-oracle rates range from 18% to 67% depending on the model
([All Smoke, No Alarm](https://arxiv.org/html/2606.18168v1)). The verifier used here is a small,
fast model at the low end of that range.

Two verifier tests also killed **zero** mutants (issues 09 and 11) while passing or being correctly
gated - validity and discriminatory power are separate properties, and only mutation scoring
separates them.

### The iteration that mattered most

`difflib` omits the "no newline at end of file" marker, and 11 of 13 fixture files lack a trailing
newline - so applying a patch silently deleted each edited file's last line, corrupting **21 of 22
runs** in the first sweep. Same model, same patch, issue-10 went from gold **1/5 failing** to
**5/5 passing** once the diff was well-formed.

Before that fix, SplitSpec looked strictly worse than the baseline. After it, it clears seven
correct patches with zero false rejections. The harness's own round-trip tests were green
throughout, because they only ever round-tripped files that ended with a newline. See
`docs/PROJECT.md` for the full changelog and `docs/HOT_TAKE.md` for the lesson.

## Reproduction

**The fastest path - reproduce the published result with no API keys, in seconds:**

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m splitspec.report --from artifacts/
```

That recomputes every number in the Results section from the run artifacts committed
to this repository. No provider keys, no Docker, no cost. It is the reproduction path
because the models are not deterministic: running the sweep yourself produces *your*
numbers, while this reproduces *ours*, from the evidence they were derived from.

Add `--output artifacts/evaluation-results.json` to write the table to disk.

**To re-run the pipeline yourself**, which needs credentials and a few hours:

Tested on Python 3.13.14, Docker 29.7.2, Linux. Model ids are pinned exactly, never by a
`-latest` alias - a floating alias means a sweep cannot be reproduced.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # add your keys locally; .env is gitignored
docker compose build sandbox
.venv/bin/python -m pytest -q            # unit suite
.venv/bin/python -m pytest -q -m docker  # sandbox end-to-end
```

`.env` needs `SPLITSPEC_<ROLE>_BASE_URL`, `_MODEL` and `_API_KEYS` for `CONTRACT`, `FIXER` and
`VERIFIER`. Any OpenAI-compatible endpoint works. A run refuses to start if a pinned model id
is not one the provider actually serves - some providers answer a retired id with HTTP 200 and
a *substitute* model rather than a 404, which would silently mislabel every result.

**One case, both modes** (~3–9 min each):

```bash
.venv/bin/python -m splitspec.run --mode baseline  --case cases/issue-07.yaml --output artifacts/issue-07-baseline
.venv/bin/python -m splitspec.run --mode splitspec --case cases/issue-07.yaml --output artifacts/issue-07-splitspec
```

**The full sweep** (~90 min if nothing rate-limits; expect it to):

```bash
.venv/bin/python -m splitspec.evaluate --cases cases/ --modes baseline,splitspec --output artifacts/evaluation-results.json
```

The sweep is **resumable**: completed pairs are skipped, failed pairs are retried. Free-tier
quotas and provider timeouts make this essential - re-run the identical command to continue.

**Expected output.** Each pair writes `artifacts/<case>-<mode>/` containing the issue contract,
the fixer's patch, the frozen verifier test and its hash, per-suite results, mutation results,
the rendered review packet, and a full `trajectory.jsonl` of every model and tool call.

**Cost.** Not measured by the harness (see above). The sweep runs entirely on free-tier
endpoints; the binding constraint is rate limits, not spend.

A read-only viewer over the artifacts lives in `apps/dashboard/` (`npm install && npm run dev`).

## Docs

| File | What it is |
|---|---|
| `docs/PROJECT.md` | Definition, case table, packet shape, improvement changelog, claims checklist |
| `docs/HOT_TAKE.md` | The main failure mode and what we would do differently |
| `docs/HLD.md` | Architecture, information boundaries, metrics, safety posture |
| `docs/LLD.md` | Module-by-module design with acceptance criteria |
| `docs/MODULES.md` | Per-module prompts, verification steps, and the hard-won findings table |
| `AGENTS.md` | Rules any AI must follow when coding here |

## Scope and limits

Results hold for the documented models, prompts, cases, and environment, and nothing wider.
Held-out testing and agent self-verification are established research areas; SplitSpec adapts
independent test generation into a reproducible maintainer workflow and measures whether it
helps. On the evidence gathered so far, it has not yet been shown to.

No claim is made that SplitSpec generalises to other repositories, replaces code review,
guarantees correctness, or is equivalent to professional QA.

## Safety

Synthetic fixture repository and synthetic data only. Every piece of agent-written code runs in
Docker with networking disabled, a memory and PID cap, and no credentials. Gold tests are never
readable from an agent workspace. The dashboard is local-only and unauthenticated - do not
expose it. Nothing is merged or deployed: every decision string is advisory and a human
decides.
