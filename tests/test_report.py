"""Module 11 reporter: recompute the result table from artifacts, with no providers."""
from __future__ import annotations

import json

from splitspec.report import load_runs
from splitspec.schemas import RunResult, TestRun


def _result(case_id: str, mode: str) -> dict:
    return RunResult(
        case_id=case_id,
        mode=mode,
        visible=TestRun(label="visible", command="pytest", passed=True, total=3),
        gold=TestRun(label="gold", command="pytest", passed=True, total=3),
        decision="ACCEPT",
    ).model_dump(mode="json")


def test_load_runs_keeps_completed_and_separates_failures(tmp_path):
    """A pair that failed is reported apart, never as a run that scored zero.

    Both are on disk as result.json. Folding a failure record into the runs list
    would put a case with no measurements into every denominator, which is the
    same "missing data is not zero" rule the metrics enforce.
    """
    ok = tmp_path / "issue-02-splitspec"
    ok.mkdir()
    (ok / "result.json").write_text(json.dumps(_result("issue-02", "splitspec")), encoding="utf-8")

    bad = tmp_path / "issue-07-baseline"
    bad.mkdir()
    (bad / "result.json").write_text(
        json.dumps({"case_id": "issue-07", "mode": "baseline", "ok": False, "error": "timed out"}),
        encoding="utf-8",
    )

    (tmp_path / "not-a-run").mkdir()  # a stray directory is skipped, not an error

    runs, failed = load_runs(tmp_path)

    assert [r.case_id for r in runs] == ["issue-02"]
    assert failed == ["issue-07-baseline"]


def test_load_runs_on_the_real_artifacts_directory():
    """The committed artifacts must stay loadable: they are the reproduction path."""
    from splitspec.config import ROOT

    artifacts = ROOT / "artifacts"
    if not artifacts.is_dir():
        return
    runs, _failed = load_runs(artifacts)
    for run in runs:
        assert run.mode in {"baseline", "splitspec"}
        assert run.case_id.startswith("issue-")
