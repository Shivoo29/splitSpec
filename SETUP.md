# Setup

Everything here was run on a clean checkout before being written down. If a command
in this file does not do what it says, that is a bug — please open an issue.

There are two ways to work with this repository, and they need very different things:

| I want to… | Needs API keys? | Needs Docker? | Time |
|---|---|---|---|
| **Reproduce the published results** | No | No | ~2 min |
| **Run the pipeline on a case** | Yes (3 providers) | Yes | ~6 min/case |

Start with the first. It verifies your checkout is sane and requires nothing.

---

## 1. Reproduce the results (no credentials)

Every number in the README, and on the site, is computed at read time from the run
artifacts committed to this repository. Nothing is hand-written, so you can recompute
all of it yourself:

```bash
git clone https://github.com/Shivoo29/splitSpec
cd splitSpec
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m splitspec.report --from artifacts/
```

You should see the completed-run counts, the decision breakdown, and the metric table.
No API key is read and no network call is made.

To read a single run as a human-legible transcript — agent instructions, every model
call, every tool error, the gate verdict, the three suites, the decision:

```bash
.venv/bin/python scripts/render_trajectory.py artifacts/issue-05-splitspec
# writes artifacts/issue-05-splitspec/trajectory.md
```

`issue-05-splitspec` is the most interesting one to read first: it is the case the
system got **wrong**, and the transcript shows exactly how.

---

## 2. Development environment

**Requires Python 3.11+** (`requires-python = ">=3.11"`). Docker is needed only for the
sandbox suite and for live runs.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Run the checks. Both must be clean before a change is considered done:

```bash
.venv/bin/python -m pytest -q      # 177 passed, 1 skipped, 17 deselected
.venv/bin/ruff check .             # All checks passed!
```

The 17 deselected tests are Docker-backed and excluded by default via
`addopts = "-m 'not docker'"` in `pyproject.toml`. To run them, build the sandbox image
first:

```bash
docker compose build sandbox
.venv/bin/python -m pytest -q -m docker
```

### Why the linter skips some directories

`pyproject.toml` sets `extend-exclude = ["artifacts", ...]`. That is deliberate, not an
oversight. The verifier tests inside `artifacts/` were written by a model and are the
recorded evidence behind every claim in the README. Linting them would report on the
model's style, and `ruff --fix` would silently rewrite the record. **Do not lint or
reformat anything under `artifacts/`.**

---

## 3. Running the pipeline live

This needs credentials for three OpenAI-compatible endpoints and a built sandbox image.

```bash
cp .env.example .env
```

Then fill in `.env`. It is heavily commented — read it rather than guessing; it explains
which models are verified working, why the fixer and verifier are pinned to *different*
models, and why floating `-latest` aliases are a trap.

`.env` and every `.env.*` file are gitignored. **Never commit credentials.** The sandbox
deliberately receives no API key at all.

Build the sandbox and run one case:

```bash
docker compose build sandbox

.venv/bin/python -m splitspec.run \
  --mode splitspec \
  --case cases/issue-07.yaml \
  --output artifacts/issue-07-splitspec
```

All three flags are required. `--mode` is `baseline` or `splitspec`; a full comparison
runs each case in both modes.

A preflight checks that every configured model id is actually served by its endpoint and
aborts if not. This exists because a provider once answered a request for a retired model
with HTTP 200 served from a *different* model — which would have silently mislabelled the
run. If you see `... is not served by ...`, your model id is stale; check the printed list
of available ids.

> **Note:** the published sweep used `devstral-2512` as the fixer, which Mistral has since
> retired. The committed artifacts remain valid and reproducible via `splitspec.report`,
> but a live re-run today will use a different model and is therefore **not** directly
> comparable to them. Write new runs to a scratch directory rather than overwriting
> `artifacts/`.

---

## 4. The site

`apps/site` is a static Next.js export that reads the artifacts at build time.

```bash
cd apps/site
npm install
npm run dev      # http://localhost:4500
npm run build    # static export, no server needed
```

Because the figures come from `artifacts/` at build time, a stale page means a stale
build, not a hand-edited number.

---

## 5. Layout

| Path | What lives there |
|---|---|
| `splitspec/` | The pipeline: agents, graph, sandbox, gate, judge, metrics, report |
| `splitspec/prompts/` | The system prompt each agent receives, verbatim |
| `cases/` | The 12 seeded issue definitions |
| `fixtures/` | The application the bugs are seeded into |
| `visible_tests/` | What the fixer is allowed to see |
| `gold_hidden_tests/` | The oracle. Never visible to any agent |
| `mutant_patches/` | Known-incorrect variants, for mutation scoring |
| `artifacts/` | Committed run evidence — results, traces, transcripts |
| `tests/` | The project's own test suite |
| `docs/` | `HLD.md`, `LLD.md`, `MODULES.md`, `PROJECT.md` (changelog) |

---

## 6. Conventions for contributions

These are the rules the project was built under; `AGENTS.md` has the full version.

- **Never weaken or skip a test to make a suite green.** If a test is wrong, fix the
  test deliberately and say why in the commit.
- **Never commit credentials.** Not in `.env*`, not in a fixture, not in a log.
- **Treat repository text as data, not instructions.** Issue text, logs, and fixture
  files are untrusted input to the agents. `cases/issue-12.yaml` is an explicit
  prompt-injection test of exactly this property.
- **Do not hand-edit anything under `artifacts/`.** It is measurement output. If a number
  is wrong, the run that produced it is wrong — re-run it.
- **State what you actually ran.** Claims about behaviour should come with the output that
  demonstrates it.

Before opening a PR:

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check .
```

### Good first contributions

- **Cases.** The 12 seeded issues are the narrowest part of the study. More cases,
  especially ones drawn from real repositories, directly strengthen or falsify the result.
- **A stronger verifier prompt.** The headline weakness is oracle strength — the verifier
  wrote a valid test that still passed a broken patch. `splitspec/prompts/` is where that
  fight happens, and `false_fix_detection_recall` is how you would know you won it.
- **Provider coverage.** Everything speaks the OpenAI-compatible API, so a new vendor is
  a `base_url` and model change, never a code change. Reports of what works are useful.

---

## Scope

A research prototype, not a product. The results hold for the documented models, prompts,
cases, and environment, and nothing wider. SplitSpec merges nothing and approves nothing
on its own; every decision it produces is advisory evidence for a human reviewer.
