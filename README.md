# SplitSpec

**Independent verification for AI-generated bug fixes.**

A fixer agent writes a patch. A separate verifier agent, isolated from the fixer, independently
writes behavioral tests from the issue and the pre-patch code. A neutral judge runs those tests
against the patch. A human maintainer receives the evidence and decides.

> The agent that writes the fix never sees the test that grades the fix.

SplitSpec does not merge, deploy, or approve anything. Its output is a review packet.

## Status

Module 0 (baseline scaffold) is complete. Modules 1–12 are specified in `docs/LLD.md` and built one
at a time; see `docs/MODULES.md`.

## Docs

| File | What it is |
|---|---|
| `docs/PROJECT.md` | Project definition, agent instructions, case table, packet shape |
| `docs/HLD.md` | Architecture, actors, information boundaries, metrics, safety posture |
| `docs/LLD.md` | Module-by-module design with acceptance criteria |
| `docs/MODULES.md` | Copy-paste implementation prompt and commit message per module |
| `AGENTS.md` | Rules any AI must follow when coding here |

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # add your model key locally; never commit .env
docker compose build sandbox
.venv/bin/python -m pytest -q
```

## Usage (available from Module 9 onward)

```bash
python -m splitspec.run --mode baseline  --case cases/issue-07.yaml --output artifacts/issue-07-baseline
python -m splitspec.run --mode splitspec --case cases/issue-07.yaml --output artifacts/issue-07-splitspec
python -m splitspec.evaluate --cases cases/ --modes baseline,splitspec --output artifacts/evaluation-results.json
python -m splitspec.mutate --case cases/issue-07.yaml --verifier-test artifacts/issue-07-splitspec/verifier_test.py --output artifacts/issue-07-mutation-results.json
```

## Safety

Synthetic fixture repository and synthetic data only. All agent-written code runs in Docker with
networking disabled and no credentials. The dashboard is a local-only, unauthenticated viewer — do
not expose it. Nothing is merged or deployed; every decision string is advisory.

Results are limited to the documented models, prompts, cases, and environment. Held-out testing and
coding-agent verification are established research areas; SplitSpec adapts independent test
generation to a reproducible maintainer workflow.
