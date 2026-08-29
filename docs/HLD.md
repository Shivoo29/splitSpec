# SplitSpec — High-Level Design

## 1. Purpose

SplitSpec answers one question under controlled conditions:

> When a repository has no curated hidden test suite, can an independent verifier agent generate
> issue-specific behavioral tests that catch shallow coding-agent fixes without rejecting too many
> correct ones?

It is a reproducible experiment plus a maintainer-facing workflow. It does not merge, deploy, or
approve anything. Its output is evidence for a human.

## 2. Core invariant of the system

> **The agent that writes the fix must never observe the test that grades the fix.**

This is enforced structurally, not by prompt instruction alone:

- The fixer and verifier run against **separate materialized workspaces** cloned from the same
  pre-patch fixture snapshot.
- The verifier's workspace is destroyed before the fixer's patch is applied anywhere.
- The verifier test is **hashed and frozen** (`frozen_sha256`) before the judge runs it. Any later
  mutation of that file invalidates the run.
- Gold hidden tests live outside every agent workspace and are mounted only into the judge's
  execution container.

Violating any of these makes a run scientifically worthless, so each is asserted in code, not left
to convention.

## 3. Actors and information boundaries

| Actor | Reads | Never reads | Produces |
|---|---|---|---|
| Contract builder | issue text, fixture tree, visible tests | patches, gold tests | `IssueContract` |
| Fixer agent | contract, pre-patch repo, visible tests | verifier test, gold tests, verifier trace | `Patch` |
| Verifier agent | contract, pre-patch repo, visible tests | any patch, fixer trace, gold tests | `VerifierTest` |
| Validity gate | frozen verifier test, original buggy repo | fixer patch | `ValidityGate` |
| Neutral judge | patch, all three suites | agent reasoning (not needed) | `TestRun[]` |
| Mutation evaluator | frozen verifier test, mutant patches | agents | `MutationResult[]` |
| Report generator | everything above | — | `review_packet.md`, `result.json` |
| Human maintainer | the report | nothing is withheld | a decision |

## 4. Architecture

```text
                       ┌─────────────────────────────┐
CLI (typer) ──────────▶│   LangGraph orchestrator    │◀──── Next.js dashboard (read-only)
                       └──────────────┬──────────────┘
                                      │ state: RunState
   ┌──────────────┬───────────────────┼──────────────────┬───────────────┐
   ▼              ▼                   ▼                  ▼               ▼
contract      fixer node        verifier node      validity gate     judge node
builder       (agent loop)      (agent loop)       (runs on buggy)   (runs 3 suites)
   │              │                   │                  │               │
   └──────────────┴──────── sandbox runner (Docker, network=none) ───────┘
                                      │
                          mutation evaluator ──▶ report generator
                                                        │
                                     artifacts/<case>-<mode>/{result.json, review_packet.md,
                                                 verifier_test.py, fixer_patch.diff, trajectory.jsonl}
```

Two graph shapes share the same nodes:

- **baseline mode**: contract → fixer → judge(visible + gold) → report.
- **splitspec mode**: contract → (fixer ‖ verifier) → freeze → validity gate →
  judge(visible + verifier + gold) → mutation → report.

The fixer and verifier branches are the only parallel step, and they cannot exchange state because
LangGraph merges their outputs only at the freeze node.

## 5. Runtime layers

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | explicit node/state graph, parallel fixer‖verifier branch, resumable |
| Agent model calls | Anthropic SDK inside LangGraph nodes | one tool loop implementation reused by both agents |
| Execution | Docker, `network_mode: none` | agent-written code never touches host or internet |
| Fixture app | FastAPI + SQLAlchemy + SQLite (PostgreSQL profile for concurrency realism) | seeded bugs must be real HTTP behavior, not toy functions |
| Test framework | pytest, JUnit XML output | machine-readable pass/fail for the judge |
| State/result store | JSON files under `artifacts/` | reproducible, diffable, no DB to stand up |
| Traces | JSONL under `trajectories/` | one line per tool call, per model call, per test run |
| Dashboard | Next.js (App Router), reads `artifacts/` | inspect runs, compare modes, show the evidence packet |

## 6. Data flow contracts

All inter-module data uses `splitspec/schemas.py`. Modules must not invent parallel dicts.

```
Case (yaml) ─▶ IssueContract ─▶ { Patch, VerifierTest } ─▶ ValidityGate ─▶ TestRun[] ─▶
MutationResult[] ─▶ RunResult ─▶ review_packet.md + evaluation-results.json
```

## 7. Metrics (computed in Module 11, never hand-entered)

- **False Fix Detection Recall** — primary. Of patches passing visible tests but failing gold tests,
  the fraction the verifier test caught.
- Correct patch acceptance rate; false rejection rate.
- Generated test validity rate (compiles ∧ runs ∧ fails on the original bug).
- Mutation score.
- Median runtime and model cost per issue, per mode.

A run whose gold tests did not execute produces **no metrics**, not zeros.

## 8. Safety posture

- Synthetic fixture repository and synthetic data only.
- Sandbox has no network and no credentials; the API key stays on the host process.
- Case 12 carries prompt-injection text; the orchestrator treats all case/repo text as untrusted
  data and keeps the system policy in a separate, non-agent-writable channel.
- Nothing is merged or deployed. Final decision strings are `ACCEPT` / `REVIEW REQUIRED` /
  `REJECT` / `ESCALATE`, all advisory.
- Case 11 (ambiguous issue) is a success when the agent escalates rather than fabricates a fix.

## 9. Non-goals

Not a coding agent product. Not a static analyzer. Not a claim that generated tests equal QA.
Not a general-repository result — findings are scoped to these 12 cases, these prompts, this model.
