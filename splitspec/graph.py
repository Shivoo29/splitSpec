"""LangGraph orchestration (Module 9).

Builds and runs the two experiment graphs over the same node functions:

- **baseline**: contract -> fixer -> judge -> report
- **splitspec**: contract -> (fixer || verifier) -> freeze -> gate -> judge ->
  mutation -> report

The fixer and verifier are the only parallel step. Each runs in its own
materialized workspace and writes only its own channel (``patch`` vs
``verifier_test``) plus its own role-scoped model/timing channel; LangGraph
merges the branches at the ``freeze`` node and nowhere before it. Because the two
branches run concurrently, every node output a parallel branch could collide on
is written to a *role-scoped* key (``fixer_model`` vs ``verifier_model``), never a
shared accumulator -- the shared ``models`` / ``timings`` aggregates are assembled
only in the report node, after the join.

The node functions are closures over a :class:`GraphContext` that carries the
injectable settings, client factory, workspace root, artifact directory, and
sandbox runners -- so the whole graph is driveable offline with :class:`FakeClient`
and a stubbed runner, and only the single live path uses real providers.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

import yaml
from langgraph.graph import END, StateGraph

from splitspec import sandbox
from splitspec.agents.fixer import run_fixer
from splitspec.agents.verifier import run_verifier
from splitspec.config import Provider, Settings
from splitspec.contracts import build_contract
from splitspec.freeze import freeze
from splitspec.gate import gate
from splitspec.judge import judge
from splitspec.llm import ModelClient
from splitspec.mutation import score_mutants
from splitspec.schemas import (
    Case,
    IssueContract,
    Mode,
    ModelUse,
    Patch,
    RunResult,
    TestRun,
    ValidityGate,
    VerifierTest,
)
from splitspec.trace import Trace

#: Roles in graph order; a run's model list is built from these pinned providers
#: via ``Provider.describe()``, which never includes a key.
_ROLES = ("contract", "fixer", "verifier")


class RunState(TypedDict, total=False):
    case: Case
    mode: Mode
    contract: IssueContract
    patch: Patch
    verifier_test: VerifierTest
    validity: ValidityGate | None
    runs: dict[str, TestRun]
    mutation: list[Any]
    trace: Trace
    cost: float
    # Role-scoped channels (written by the parallel fixer/verifier/contract nodes
    # and only aggregated later, so they never collide):
    contract_model: ModelUse
    fixer_model: ModelUse
    verifier_model: ModelUse
    time_contract: float
    time_fixer: float
    time_verifier: float
    time_freeze: float
    time_gate: float
    time_judge: float
    time_mutation: float
    # Final aggregates, assembled in the report node after the parallel join:
    models: list[ModelUse]
    timings: dict[str, float]
    degraded: bool
    degraded_reason: str
    result: RunResult


JudgeRunner = Callable[..., sandbox.ExecResult]


@dataclass
class GraphContext:
    """Everything the node closures need, so tests can stub the moving parts."""

    settings: Settings
    make_client: Callable[[Provider], ModelClient]
    workspace_root: Path
    artifact_dir: Path
    clock: Callable[[], float] = field(default=time.monotonic)
    judge_runner: JudgeRunner | None = None
    gate_runner: Callable[..., sandbox.ExecResult] | None = None
    mutation_runner: Callable[..., sandbox.ExecResult] | None = None


def _role_model(provider: Provider) -> ModelUse:
    return ModelUse(
        role=provider.role, base_url=provider.base_url, model=provider.model,
    )


def _repo_context(case: Case) -> str:
    """A small, deterministic repo summary handed to the contract builder."""
    app_root = sandbox.FIXTURE / "app"
    files = []
    if app_root.is_dir():
        for p in sorted(app_root.rglob("*.py")):
            files.append(p.relative_to(sandbox.FIXTURE).as_posix())
    return "EventPulse fixture files:\n" + "\n".join(files) if files else "EventPulse API"


# ---------------------------------------------------------------------------
# Node functions (closures over ctx)
# ---------------------------------------------------------------------------


def _contract_node(ctx: GraphContext, state: RunState) -> dict[str, Any]:
    case = state["case"]
    start = ctx.clock()
    client = ctx.make_client(ctx.settings.provider("contract"))
    contract = build_contract(case, _repo_context(case), client, state["trace"])
    return {
        "contract": contract,
        "contract_model": _role_model(ctx.settings.contract),
        "time_contract": ctx.clock() - start,
    }


def _fixer_node(ctx: GraphContext, state: RunState) -> dict[str, Any]:
    case = state["case"]
    start = ctx.clock()
    client = ctx.make_client(ctx.settings.fixer)
    ws = sandbox.materialize(case, "fixer", ctx.workspace_root)
    try:
        patch = run_fixer(
            state["contract"], case, ws, client, ctx.settings, state["trace"]
        )
    finally:
        ws.destroy()
    return {
        "patch": patch,
        "fixer_model": _role_model(ctx.settings.fixer),
        "time_fixer": ctx.clock() - start,
    }


def _verifier_node(ctx: GraphContext, state: RunState) -> dict[str, Any]:
    case, contract = state["case"], state["contract"]
    start = ctx.clock()
    client = ctx.make_client(ctx.settings.verifier)
    ws = sandbox.materialize(case, "verifier", ctx.workspace_root)
    try:
        test = run_verifier(contract, case, ws, client, ctx.settings, state["trace"])
    finally:
        ws.destroy()
    return {
        "verifier_test": test,
        "verifier_model": _role_model(ctx.settings.verifier),
        "time_verifier": ctx.clock() - start,
    }


def _freeze_node(ctx: GraphContext, state: RunState) -> dict[str, Any]:
    start = ctx.clock()
    frozen = freeze(state["verifier_test"], ctx.artifact_dir)
    state["trace"].event(
        "graph", "freeze",
        case_id=state["case"].id, mode=state["mode"],
        filename=frozen.filename, frozen_sha256=frozen.frozen_sha256,
    )
    return {"verifier_test": frozen, "time_freeze": ctx.clock() - start}


def _gate_node(ctx: GraphContext, state: RunState) -> dict[str, Any]:
    start = ctx.clock()
    result = gate(
        state["verifier_test"], state["case"], ctx.workspace_root, state["trace"],
        runner=ctx.gate_runner,
    )
    return {"validity": result, "time_gate": ctx.clock() - start}


def _judge_node(ctx: GraphContext, state: RunState) -> dict[str, Any]:
    start = ctx.clock()
    # The frozen artifact path is handed to the judge only when a gated test
    # earned the right to grade: an invalid test is recorded (validity-rate
    # metric) but must not judge the patch.
    frozen_dir = (
        ctx.artifact_dir
        if state["mode"] == "splitspec"
        and state.get("validity") is not None
        and bool(state["validity"].passed)
        else None
    )
    runs = judge(
        state["case"], state["patch"], frozen_dir, state["mode"],
        ctx.workspace_root, state["trace"], runner=ctx.judge_runner,
    )
    return {"runs": runs, "time_judge": ctx.clock() - start}


def _mutation_node(ctx: GraphContext, state: RunState) -> dict[str, Any]:
    start = ctx.clock()
    results = score_mutants(
        state["case"], ctx.artifact_dir, ctx.workspace_root, state["trace"],
        runner=ctx.mutation_runner,
    )
    state["trace"].event(
        "graph", "mutation",
        case_id=state["case"].id, mode=state["mode"],
        killed=sum(1 for r in results if r.killed),
        denominator=len(results),
        path=str(ctx.artifact_dir / "mutation_results.json"),
    )
    return {"mutation": results, "time_mutation": ctx.clock() - start}


def _report_node(ctx: GraphContext, state: RunState) -> dict[str, Any]:
    case, mode = state["case"], state["mode"]
    result = RunResult(case_id=case.id, mode=mode)

    _write_text_artifacts(ctx, state)

    result.contract = state.get("contract")
    result.patch = state.get("patch")
    result.verifier_test = state.get("verifier_test")
    result.validity = state.get("validity")
    result.visible = state.get("runs", {}).get("visible")
    result.verifier = state.get("runs", {}).get("verifier")
    result.gold = state.get("runs", {}).get("gold")
    result.mutation = list(state.get("mutation", []))
    result.models = _role_ordered_models(ctx, state)
    result.cost_usd = round(state.get("cost", 0.0), 6)
    result.runtime_sec = round(_total_time(state), 3)
    result.artifact_dir = str(ctx.artifact_dir)
    result.degraded = bool(state.get("degraded", False))
    result.degraded_reason = state.get("degraded_reason", "")

    _write_packet(ctx, state, result)
    (ctx.artifact_dir / "result.json").write_text(
        result.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    state["trace"].event(
        "report", "written",
        case_id=case.id, mode=mode, artifact_dir=result.artifact_dir,
        degraded=result.degraded, cost_usd=result.cost_usd,
        runtime_sec=result.runtime_sec,
        models=[(m.role, m.model) for m in result.models],
    )
    return {"result": result}


def _role_ordered_models(ctx: GraphContext, state: RunState) -> list[ModelUse]:
    """The pinned provider for each role that actively ran, in graph order.

    Built from ``Provider.describe()`` (role/base_url/model/key_count), never from
    raw settings, and never including an API key. A role that did not run (e.g. no
    verifier in baseline mode) is skipped.
    """
    channel = {
        "contract": "contract_model",
        "fixer": "fixer_model",
        "verifier": "verifier_model",
    }
    models: list[ModelUse] = []
    for role in _ROLES:
        if state.get(channel[role]) is not None:
            models.append(_model_from_describe(ctx.settings.provider(role).describe()))
    return models


def _model_from_describe(d: dict) -> ModelUse:
    return ModelUse(role=d["role"], base_url=d["base_url"], model=d["model"])


def _total_time(state: RunState) -> float:
    keys = (
        "time_contract", "time_fixer", "time_verifier", "time_freeze",
        "time_gate", "time_judge", "time_mutation",
    )
    return sum(state.get(k, 0.0) for k in keys)


def _write_text_artifacts(ctx: GraphContext, state: RunState) -> None:
    """The §13 text artifacts other than the ones freeze/judge already wrote."""
    d = ctx.artifact_dir
    d.mkdir(parents=True, exist_ok=True)
    case = state["case"]

    contract = state.get("contract")
    if contract is not None:
        (d / "issue_contract.yaml").write_text(
            yaml.safe_dump(contract.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )

    (d / "fixer_patch.diff").write_text(
        (state.get("patch") or Patch(case_id=case.id, diff="")).diff or "",
        encoding="utf-8",
    )

    (d / "visible_tests.txt").write_text(
        "\n".join(sorted(case.visible_tests)) + "\n", encoding="utf-8"
    )

    (d / "gold_hidden_tests.txt").write_text(
        "\n".join(sorted(case.gold_tests)) + "\n", encoding="utf-8"
    )

    vtest = state.get("verifier_test")
    if vtest is not None:
        (d / "verifier_tests.txt").write_text(vtest.contents, encoding="utf-8")


def _write_packet(ctx: GraphContext, state: RunState, result: RunResult) -> None:
    """Minimal review packet stub (fully rendered by Module 11)."""
    d = ctx.artifact_dir
    lines = [
        f"# SplitSpec Review Packet - Issue {state['case'].id}",
        "",
        "## Decision",
        result.decision,
        "",
        "## Issue",
        state["case"].title,
        "",
        "## Candidate patch",
        f"- Files changed: {', '.join(result.patch.files_changed) if result.patch else 'n/a'}",
        "",
        "## Visible tests",
        _suite_line(result.visible),
        "",
        "## Gold hidden evaluator",
        _suite_line(result.gold),
        "",
        "## Residual risks",
        "- Full review packet rendering lands with Module 11.",
    ]
    (d / "review_packet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _suite_line(run: TestRun | None) -> str:
    if run is None:
        return "n/a"
    verdict = "PASS" if run.passed else "FAIL"
    return f"{verdict} - {run.total} tests, {run.failures} failed, {run.errors} errors"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _state_graph(ctx: GraphContext, mode: Mode):
    """Build the state graph for ``mode`` over the shared node closures."""
    g = StateGraph(RunState)
    g.add_node("contract", lambda s: _contract_node(ctx, s))
    g.add_node("fixer", lambda s: _fixer_node(ctx, s))
    g.add_node("judge", lambda s: _judge_node(ctx, s))
    g.add_node("report", lambda s: _report_node(ctx, s))

    if mode == "baseline":
        g.add_edge("__start__", "contract")
        g.add_edge("contract", "fixer")
        g.add_edge("fixer", "judge")
        g.add_edge("judge", "report")
        g.add_edge("report", END)
        return g

    # splitspec
    g.add_node("verifier", lambda s: _verifier_node(ctx, s))
    g.add_node("freeze", lambda s: _freeze_node(ctx, s))
    g.add_node("gate", lambda s: _gate_node(ctx, s))
    g.add_node("mutation", lambda s: _mutation_node(ctx, s))

    g.add_edge("__start__", "contract")
    # Fixer and verifier are the only parallel step; both feed freeze and nothing
    # else, so their outputs are never visible to each other.
    g.add_edge("contract", "fixer")
    g.add_edge("contract", "verifier")
    g.add_edge("fixer", "freeze")
    g.add_edge("verifier", "freeze")
    g.add_edge("freeze", "gate")
    g.add_edge("gate", "judge")
    g.add_edge("judge", "mutation")
    g.add_edge("mutation", "report")
    g.add_edge("report", END)
    return g


def execute(ctx: GraphContext, case: Case, mode: Mode) -> RunResult:
    """Run one case/mode through the graph and return the written :class:`RunResult`."""
    app = _state_graph(ctx, mode).compile()
    initial: RunState = {
        "case": case,
        "mode": mode,
        "trace": Trace(ctx.artifact_dir / "trajectory.jsonl"),
        "cost": 0.0,
        "degraded": False,
        "degraded_reason": "",
    }
    final = app.invoke(initial)
    return final["result"]
