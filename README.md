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
that writes the patch is also the thing that decides the patch is finished — it stops when the
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
| **Judge** | The patch, all three suites | — calls no model, infers nothing |

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

Measured from real runs in `artifacts/` — Docker sandbox, `--network none`, real models. No
figure below is simulated.

**Models:** contract `openai/gpt-oss-120b` (Groq) · fixer `devstral-2512` (Mistral) · verifier
`gemini-3.1-flash-lite` (Google). Fixer and verifier are different models on different
providers.

**Test suite:** 175 unit tests + 17 Docker end-to-end tests pass, 1 skipped.

**Gold-oracle validation** — every seeded bug is caught by its gold suite, and case 11 (no
seeded bug) passes, across all 12 cases with zero errors:

| | visible on buggy code | gold on buggy code |
|---|---|---|
| issues 01–09, 12 | pass | **fail** |
| issue 10 (inverted by design) | **fail** | fail |
| issue 11 (no bug) | pass | pass |

**Sweep, 12 cases × 2 modes.** Partial: 7 of 24 pairs failed on provider read timeouts and are
pending re-run. Every rate is reported with its denominator.

| Metric | Value | Denominator |
|---|---|---|
| False-fix detection recall | **0 / 2** | shallow fixes with a verifier verdict |
| Generated test validity rate | **7 / 7** | tests that reached the gate |
| Mutation score (pooled) | **25 / 28** | scored mutants |
| Median runtime, baseline | 293 s | 7 completed runs |
| Median runtime, splitspec | 287 s | 8 completed runs |
| Model cost | **not measured** | agent loops drop token usage before it reaches the result |

### The honest result

**The verifier did not catch either shallow fix it was given.** On issues 05 and 10 the fixer's
patch passed the visible suite, failed the gold suite, and the independent verifier test
*passed* — so SplitSpec returned ACCEPT on two patches the hidden oracle says are broken. That
is a false accept, twice, and it is the central claim of this project not being supported on
the cases measured so far.

Two things should be separated from that:

- **The validity gate works.** Seven of seven generated tests compiled, ran, and failed on the
  original bug. An earlier run on issue-07 produced a plausible-looking test using
  `asyncio.gather` over a single event loop — which serialises ASGI requests, so there was no
  race to catch — and the gate correctly rejected it as non-discriminating. The gate accepts
  good tests and rejects toothless ones.
- **The generated tests have real discriminatory power** where they exist: 25 of 28 scored
  mutants killed, against 0 for a deliberately trivial test.

So the machinery works and the hypothesis is, on this evidence, unconfirmed. A generated test
can be valid, kill mutants, and still miss the specific shallow fix in front of it. See
`docs/PROJECT.md` for the improvement changelog and `docs/HOT_TAKE.md` for what we would build
differently.

## Reproduction

Tested on Python 3.13.14, Docker 29.7.2, Linux. Model ids are pinned exactly, never by a
`-latest` alias — a floating alias means a sweep cannot be reproduced.

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
is not one the provider actually serves — some providers answer a retired id with HTTP 200 and
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
quotas and provider timeouts make this essential — re-run the identical command to continue.

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
readable from an agent workspace. The dashboard is local-only and unauthenticated — do not
expose it. Nothing is merged or deployed: every decision string is advisory and a human
decides.
