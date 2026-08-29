"""Module 9: LangGraph orchestration tests.

The unit tests drive the whole graph offline: FakeClient for the model layer and
a fake Docker runner (writing the JUnit XML the judge reads) so not one test needs
Docker or a real model. The single behavioral test marked ``@pytest.mark.docker``
runs the real sandbox end to end with a scripted client.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from splitspec import sandbox
from splitspec.config import ROOT, Provider, Settings
from splitspec.graph import GraphContext, _fixer_node, _verifier_node, execute
from splitspec.llm import Completion, FakeClient, ModelReply
from splitspec.schemas import Case, Confidence, IssueContract, RunResult
from splitspec.trace import Trace

#: PROJECT.md §13 artifact set for a splitspec run.
ARTIFACTS = {
    "issue_contract.yaml",
    "fixer_patch.diff",
    "verifier_test.py",
    "visible_tests.txt",
    "verifier_tests.txt",
    "gold_hidden_tests.txt",
    "mutation_results.json",
    "trajectory.jsonl",
    "result.json",
    "review_packet.md",
}
#: A baseline run has no verifier (so no verifier artifacts) and no mutation step.
ARTIFACTS_BASELINE = ARTIFACTS - {
    "verifier_test.py", "verifier_tests.txt", "mutation_results.json",
}


def load_case(case_id: str = "issue-07") -> Case:
    data = yaml.safe_load((ROOT / "cases" / f"{case_id}.yaml").read_text())
    return Case.model_validate(data)


def _settings() -> Settings:
    def p(role: str) -> Provider:
        return Provider(role=role, base_url=f"http://{role}.x", model=f"model-{role}")

    return Settings(fixer=p("fixer"), verifier=p("verifier"), contract=p("contract"))


CONTRACT = {
    "case_id": "issue-07",
    "summary": "Duplicate registration under concurrency.",
    "invariants": ["At most one registration per (user, event)."],
    "confidence": "high",
}
VERIFIER = {
    "filename": "test_verify.py",
    "contents": "async def test_dup(client):\n    assert True\n",
    "run_command": "pytest test_verify.py",
    "invariant": "at most one registration per (user, event)",
    "confidence": "high",
}


def _client_for(provider: Provider) -> FakeClient:
    """A FakeClient that 'completes' each role without any Docker/network."""
    if provider.role == "contract":
        return FakeClient(responses=[Completion(text=json.dumps(CONTRACT), model="model-contract")])
    if provider.role == "verifier":
        return FakeClient(
            replies=[ModelReply(text=json.dumps(VERIFIER), finish_reason="stop", model="model-verifier")]
        )
    # fixer: report an empty patch (no tool calls -> no Docker)
    fixer_reply = [ModelReply(text="no change needed", finish_reason="stop", model="model-fixer")]
    return FakeClient(replies=fixer_reply)


class FakeJudge:
    """A stand-in for sandbox.run_in_sandbox that writes the judge's JUnit XML."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, ws, command, timeout, mounts=None):
        self.calls.append(" ".join(command))
        label = next(a for a in command if a.startswith("--junitxml=")).split(".junit/")[1].split(".xml")[0]
        (ws.path / ".junit").mkdir(parents=True, exist_ok=True)
        (ws.path / ".junit" / f"{label}.xml").write_text(
            f'<testsuites><testsuite name="{label}" tests="1" failures="0" errors="0"/></testsuites>',
            encoding="utf-8",
        )
        return sandbox.ExecResult(exit_code=0, stdout="1 passed", stderr="", duration_sec=0.1)


def _fake_gate(ws, command, timeout):
    # "1 failed" with no crash markers => the test fails on the bug => valid.
    return sandbox.ExecResult(exit_code=1, stdout="1 failed", stderr="", duration_sec=0.1)


def _fake_mutation(ws, command, timeout, mounts=None):
    # The frozen test passes on every mutant, so no mutant is "killed" by it. Keeps
    # the graph's mutation node deterministic and Docker-free in unit tests.
    return sandbox.ExecResult(exit_code=0, stdout="1 passed", stderr="", duration_sec=0.1)


def _ctx(tmp_path, *, settings=None) -> GraphContext:
    return GraphContext(
        settings=settings or _settings(),
        make_client=_client_for,
        workspace_root=tmp_path / "ws",
        artifact_dir=tmp_path / "art",
        gate_runner=_fake_gate,
        judge_runner=FakeJudge(),
        mutation_runner=_fake_mutation,
    )


# ---------------------------------------------------------------------------
# Full runs in both modes produce the complete artifact set
# ---------------------------------------------------------------------------


def test_splitspec_run_produces_every_project13_artifact(tmp_path):
    execute(_ctx(tmp_path), load_case(), "splitspec")

    assert "case_id" in RunResult.model_fields
    names = {p.name for p in (tmp_path / "art").iterdir()}
    assert ARTIFACTS <= names, f"missing: {ARTIFACTS - names}"
    # Every §13 file is non-trivial
    assert (tmp_path / "art" / "fixer_patch.diff").exists()
    assert (tmp_path / "art" / "trajectory.jsonl").read_text(encoding="utf-8").strip()
    assert (tmp_path / "art" / "mutation_results.json").read_text(encoding="utf-8").strip()
    assert (tmp_path / "art" / "review_packet.md").read_text(encoding="utf-8").strip()
    assert RunResult.model_validate_json((tmp_path / "art" / "result.json").read_text())


def test_baseline_run_produces_its_artifact_subset_without_verifier(tmp_path):
    ctx = _ctx(tmp_path)
    result = execute(ctx, load_case(), "baseline")

    names = {p.name for p in (tmp_path / "art").iterdir()}
    assert ARTIFACTS_BASELINE <= names, f"missing: {ARTIFACTS_BASELINE - names}"
    # baseline has no verifier branch
    assert "verifier_test.py" not in names
    assert "mutation_results.json" not in names
    assert result.verifier_test is None
    assert result.mutation == []


# ---------------------------------------------------------------------------
# Fixer/verifier isolation across the parallel branches
# ---------------------------------------------------------------------------


def test_parallel_branches_use_disjoint_workspaces_with_no_cross_artifacts(tmp_path, monkeypatch):
    """The fixer and verifier run in separate workspaces; neither branch's
    workspace ever contains the other role's artifact, and the graph joins them
    only after both finished (both models recorded, both products present)."""
    materialized: dict[str, Path] = {}

    real_materialize = sandbox.materialize

    def spy_materialize(case, role, root):
        ws = real_materialize(case, role, root)
        materialized[role] = ws.path
        return ws

    monkeypatch.setattr(sandbox, "materialize", spy_materialize)
    # Keep the workspaces on disk so we can inspect them after the run.
    monkeypatch.setattr(sandbox.Workspace, "destroy", lambda self: None)
    try:
        ctx = _ctx(tmp_path)
        result = execute(ctx, load_case(), "splitspec")
    finally:
        shutil.rmtree(tmp_path / "ws", ignore_errors=True)

    fixer_ws, verifier_ws = materialized["fixer"], materialized["verifier"]
    assert fixer_ws != verifier_ws

    fixer_files = {p.relative_to(fixer_ws).as_posix() for p in fixer_ws.rglob("*") if p.is_file()}
    verifier_files = {p.relative_to(verifier_ws).as_posix() for p in verifier_ws.rglob("*") if p.is_file()}

    # The verifier's test never lands in the fixer's workspace...
    assert "verifier_test.py" not in fixer_files
    assert not any(f.endswith("_test.py") or "verifier" in f.lower() for f in fixer_files)
    # ...and the fixer's patch never lands in the verifier's workspace.
    assert not any("fixer_patch" in f for f in verifier_files)

    # Both branches joined: each produced its product and its model is recorded.
    assert result.patch is not None and result.verifier_test is not None
    roles = {m.role for m in result.models}
    assert {"fixer", "verifier"} <= roles


def test_branch_nodes_emit_only_their_own_product(tmp_path):
    """Direct: the fixer node never emits verifier state and vice versa."""
    ctx = _ctx(tmp_path)
    case = load_case()
    state = {
        "case": case,
        "contract": IssueContract(case_id=case.id, summary="s", invariants=["i"], confidence=Confidence.high),
        "trace": Trace(tmp_path / "trace.jsonl"),
        "mode": "splitspec",
    }
    fixer_out = _fixer_node(ctx, state)
    verifier_out = _verifier_node(ctx, state)
    assert "patch" in fixer_out and "verifier_test" not in fixer_out
    assert "verifier_test" in verifier_out and "patch" not in verifier_out


# ---------------------------------------------------------------------------
# result.json: models recorded, no API key anywhere
# ---------------------------------------------------------------------------


def test_result_models_are_recorded_without_any_key(tmp_path):
    ctx = _ctx(tmp_path)
    execute(ctx, load_case(), "splitspec")

    result = json.loads((tmp_path / "art" / "result.json").read_text())
    roles = [m["role"] for m in result["models"]]
    assert roles == ["contract", "fixer", "verifier"]
    # No key material may appear anywhere in the result.
    blob = json.dumps(result)
    for needle in ("api_key", "api_keys", "key=", "Bearer", "sk-"):
        assert needle.lower() not in blob.lower()
    for m in result["models"]:
        assert "key" not in m


# ---------------------------------------------------------------------------
# The trace (trajectory.jsonl) never leaks gold content
# ---------------------------------------------------------------------------


def test_trajectory_contains_no_gold_hidden_reference(tmp_path):
    ctx = _ctx(tmp_path)
    execute(ctx, load_case(), "splitspec")
    trajectory = (tmp_path / "art" / "trajectory.jsonl").read_text(encoding="utf-8")
    assert "gold_hidden" not in trajectory
    # The gold suite is still run by the judge (recorded in the result).
    result = json.loads((tmp_path / "art" / "result.json").read_text())
    assert result["gold"] is not None


# ---------------------------------------------------------------------------
# A run that raises still writes a result.json and the sweep continues
# ---------------------------------------------------------------------------


def test_evaluate_failing_case_writes_error_and_continues(tmp_path, monkeypatch):
    """A pair that raises mid-run still writes its result.json and does NOT abort
    the sweep: every other case still runs and lands in evaluation-results.json."""
    import splitspec.evaluate as ev

    mocked_cases = tmp_path / "cases"
    mocked_cases.mkdir(parents=True, exist_ok=True)
    (mocked_cases / "issue-05.yaml").write_text(
        yaml.safe_dump({"id": "issue-05", "title": "b", "issue_text": "x", "fixture": "eventpulse"})
    )
    (mocked_cases / "issue-07.yaml").write_text(
        yaml.safe_dump({"id": "issue-07", "title": "a", "issue_text": "x", "fixture": "eventpulse"})
    )

    calls = []

    def fake_run_case(case, mode, output, settings=None):
        calls.append((case.id, mode))
        if case.id == "issue-05":
            raise RuntimeError("provider quota exhausted")
        result = RunResult(case_id=case.id, mode=mode, artifact_dir=str(output))
        result_json = Path(output) / "result.json"
        result_json.parent.mkdir(parents=True, exist_ok=True)
        result_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr(ev, "run_case", fake_run_case)
    monkeypatch.setattr(ev.Settings, "from_env", staticmethod(lambda: _settings()))

    eval_out = tmp_path / "eval.json"
    ev.evaluate(cases=mocked_cases, modes="splitspec", output=eval_out, parallel=1, force=True)

    # Both pairs were attempted - the failure did not stop the sweep.
    assert ("issue-05", "splitspec") in calls
    assert ("issue-07", "splitspec") in calls
    summary = json.loads(eval_out.read_text())
    assert summary["total"] == 2
    assert summary["ok"] == 1
    assert summary["results"]["issue-05-splitspec"]["ok"] is False
    assert summary["results"]["issue-07-splitspec"].get("ok", True) is True
    # The failed pair still wrote its own result.json.
    assert (tmp_path / "issue-05-splitspec" / "result.json").is_file()



def test_run_pair_records_failed_case_as_result_json(tmp_path, monkeypatch):
    import splitspec.evaluate as ev

    case = load_case()

    def boom(case, mode, output, settings=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(ev, "run_case", boom)
    out = tmp_path / "art" / "issue-07-splitspec"
    record = ev._run_pair(case, "splitspec", out, _settings(), force=False)
    assert record["ok"] is False
    assert "boom" in record["error"]
    result_json = out / "result.json"
    assert result_json.is_file()
    assert json.loads(result_json.read_text())["ok"] is False


def test_run_pair_skips_complete_case_unless_force(tmp_path, monkeypatch):
    import splitspec.evaluate as ev

    case = load_case()
    out = tmp_path / "art" / "issue-07-splitspec"
    out.mkdir(parents=True, exist_ok=True)
    complete = RunResult(case_id=case.id, mode="splitspec", artifact_dir=str(out))
    (out / "result.json").write_text(complete.model_dump_json(indent=2), encoding="utf-8")

    called = []
    monkeypatch.setattr(
        ev, "run_case", lambda *a, **k: (called.append("x"), RunResult(case_id=case.id, mode="splitspec"))[1]
    )

    # Not forced: the existing complete result.json is used, run_case not called.
    record = ev._run_pair(case, "splitspec", out, _settings(), force=False)
    assert called == []
    assert record["case_id"] == case.id

    assert ev._complete(out / "result.json") is True


def test_run_pair_force_reruns(tmp_path, monkeypatch):
    import splitspec.evaluate as ev

    case = load_case()
    out = tmp_path / "art" / "issue-07-splitspec"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(
        RunResult(case_id=case.id, mode="splitspec", artifact_dir=str(out)).model_dump_json(indent=2),
        encoding="utf-8",
    )
    called = []
    monkeypatch.setattr(
        ev, "run_case",
        lambda *a, **k: (called.append(case.id), RunResult(case_id=case.id, mode="splitspec"))[1],
    )
    ev._run_pair(case, "splitspec", out, _settings(), force=True)
    assert called == [case.id]


# ---------------------------------------------------------------------------
# Node boundary: a planted gold test / cross role artifact raises immediately
# ---------------------------------------------------------------------------


def test_fixer_and_verifier_guard_thresholds(tmp_path):
    """The role boundary is enforced by each agent's own entry assertion; the
    graph relies on it, so a planted cross-role artifact aborts the branch."""
    from splitspec.agents.fixer import run_fixer
    from splitspec.agents.verifier import run_verifier

    case = load_case()
    contract = IssueContract(case_id=case.id, summary="s", invariants=["i"])
    client = FakeClient(replies=[ModelReply(text="done", finish_reason="stop")])

    fixer_ws = sandbox.materialize(case, "fixer", tmp_path / "f")
    verifier_ws = sandbox.materialize(case, "verifier", tmp_path / "v")
    try:
        # verifier artifact planted in fixer workspace -> fixer must refuse
        (fixer_ws.path / "verifier_test.py").write_text("x=1", encoding="utf-8")
        with pytest.raises(AssertionError, match="verifier"):
            run_fixer(contract, case, fixer_ws, client, _settings(), Trace(tmp_path / "t1.jsonl"))

        # fixer artifact planted in verifier workspace -> verifier must refuse
        (verifier_ws.path / "fixer_patch.diff").write_text("diff", encoding="utf-8")
        with pytest.raises(AssertionError, match="fixer"):
            run_verifier(contract, case, verifier_ws, client, _settings(), Trace(tmp_path / "t2.jsonl"))
    finally:
        fixer_ws.destroy()
        verifier_ws.destroy()


# ---------------------------------------------------------------------------
# Real sandbox end to end (docker)
# ---------------------------------------------------------------------------


@pytest.mark.docker
def test_docker_splitspec_run_end_to_end_with_scripted_client(tmp_path):
    ctx = GraphContext(
        settings=_settings(),
        make_client=_client_for,
        workspace_root=tmp_path / "ws",
        artifact_dir=tmp_path / "art",
        gate_runner=None,      # real sandbox gate
        judge_runner=None,     # real sandbox judge
        mutation_runner=None,  # real sandbox mutant scoring
    )
    result = execute(ctx, load_case(), "splitspec")

    names = {p.name for p in (tmp_path / "art").iterdir()}
    assert ARTIFACTS <= names
    assert result.visible is not None and result.gold is not None
    roles = {m.role for m in result.models}
    assert {"fixer", "verifier"} <= roles


def test_resume_retries_a_failed_pair(tmp_path, monkeypatch):
    """A pair that failed must be RE-RUN on resume, not skipped as complete.

    A failure record only carries case_id/mode beyond its ok/error keys, and every
    other RunResult field defaults - so it validates as a RunResult. If _complete
    trusted that, resume would skip exactly the pairs a provider quota killed,
    which is the one job resume has.
    """
    import splitspec.evaluate as ev

    case = load_case()
    out = tmp_path / "issue-05-splitspec"
    ev._write_error(out / "result.json", case, "splitspec", "429 quota exhausted")
    assert ev._complete(out / "result.json") is False

    calls = []

    def _fake_run_case(c, mode, artifact_dir, settings=None):
        calls.append(c.id)
        return RunResult(case_id=c.id, mode=mode, artifact_dir=str(artifact_dir))

    monkeypatch.setattr(ev, "run_case", _fake_run_case)
    record = ev._run_pair(case, "splitspec", out, _settings(), force=False)
    assert calls == [case.id], "resume skipped a failed pair instead of retrying it"
    assert record.get("ok") is not False
