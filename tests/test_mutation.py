"""Module 10: mutation evaluator tests.

Score *decision* logic (killed vs passed vs import-crash, the manifest read, the
artifact/determinism contract) is covered offline with an injected runner that
never touches Docker or the network. The two behavioral scoring tests are marked
``@pytest.mark.docker`` and run the frozen test against the real mutant overlays
in the sandbox: a deliberately weak test must score ~0 and the gold test must
score high, bracketing the mutation metric.
"""
from __future__ import annotations

import json
import os

import pytest
import yaml

from splitspec import sandbox
from splitspec.config import ROOT
from splitspec.freeze import VERIFIER_TEST_FILENAME, freeze
from splitspec.mutation import MUTATION_RESULTS_FILENAME, score_mutants
from splitspec.schemas import Case, Confidence, VerifierTest
from splitspec.trace import Trace


def load_case(case_id: str) -> Case:
    data = yaml.safe_load((ROOT / "cases" / f"{case_id}.yaml").read_text())
    return Case.model_validate(data)


def _test(case_id: str = "issue-07", contents: str = "def test_x():\n    assert True\n") -> VerifierTest:
    return VerifierTest(
        case_id=case_id,
        filename="test_probe.py",
        contents=contents,
        run_command="pytest test_probe.py",
        invariant="a behavioral invariant",
        confidence=Confidence.high,
    )


def _exec(stdout: str, stderr: str = "", exit_code: int = 0) -> sandbox.ExecResult:
    return sandbox.ExecResult(
        exit_code=exit_code, stdout=stdout, stderr=stderr, duration_sec=0.1,
    )


def _freeze(test: VerifierTest, tmp_path):
    frozen_dir = tmp_path / "frozen"
    frozen = freeze(test, frozen_dir)
    return frozen_dir, frozen


def _runner(*outcomes: sandbox.ExecResult):
    """A fake runner that hands back one canned outcome per mutant invocation."""
    seq = iter(outcomes)

    def runner(ws, command, timeout, mounts=None):
        return next(seq)

    return runner


# ---------------------------------------------------------------------------
# Decision logic, offline (injected runner, no Docker)
# ---------------------------------------------------------------------------


def test_manifest_is_issue07_and_returns_five_mutants(tmp_path):
    """issue-07's manifest has 5 mutants and each gets a MutationResult."""
    frozen_dir, _ = _freeze(_test(), tmp_path)
    results = score_mutants(
        load_case("issue-07"), frozen_dir, tmp_path / "ws",
        Trace(tmp_path / "t.jsonl"), runner=_runner(*(_exec("1 passed") for _ in range(5))),
    )
    assert len(results) == 5
    assert [r.mutant_id for r in results] == ["m07-1", "m07-2", "m07-3", "m07-4", "m07-5"]


def test_issue11_manifest_has_three_mutants_not_four(tmp_path):
    """The manifest.yaml glob trap: issue-11 has 3 mutants, never 3 + manifest.yaml."""
    frozen_dir, _ = _freeze(_test("issue-11"), tmp_path)
    results = score_mutants(
        load_case("issue-11"), frozen_dir, tmp_path / "ws",
        Trace(tmp_path / "t.jsonl"), runner=_runner(*(_exec("1 passed") for _ in range(3))),
    )
    assert len(results) == 3


def test_test_that_fails_on_mutant_is_killed(tmp_path):
    frozen_dir, _ = _freeze(_test(), tmp_path)
    results = score_mutants(
        load_case("issue-07"), frozen_dir, tmp_path / "ws",
        Trace(tmp_path / "t.jsonl"),
        runner=_runner(_exec("1 failed in 0.1s", exit_code=1), *(_exec("1 passed") for _ in range(4))),
    )
    assert results[0].killed is True
    assert "failed on this mutant" in results[0].detail
    assert all(not r.killed for r in results[1:])


def test_import_break_is_killed_false_and_distinct_from_live_pass(tmp_path):
    """A mutant that crashes the test on import is not 'killed' — and that finding
    must be distinguishable from a test that ran and passed."""
    frozen_dir, _ = _freeze(_test(), tmp_path)
    crash = _exec("", stderr="ModuleNotFoundError: No module named 'app'", exit_code=1)
    results = score_mutants(
        load_case("issue-07"), frozen_dir, tmp_path / "ws",
        Trace(tmp_path / "t.jsonl"),
        runner=_runner(crash, *(_exec("1 passed in 0.1s") for _ in range(4))),
    )
    # The import-crashed mutant: not killed, and the reason is a did-not-run.
    assert results[0].killed is False
    assert "import/collection failure" in results[0].detail
    # The live-pass mutants: not killed, but for the opposite reason.
    assert all(r.killed is False for r in results[1:])
    assert all("passed on this mutant" in r.detail for r in results[1:])
    # The two findings are distinct facts, never conflated.
    assert results[0].detail != results[1].detail
    assert "import" not in results[1].detail
    assert "passed" not in results[0].detail


def test_hash_mismatch_aborts_before_any_mutant_runs(tmp_path):
    """Tampering with a frozen test makes score_mutants abort before the manifest runs."""
    frozen_dir, _ = _freeze(_test(), tmp_path)
    test_path = frozen_dir / VERIFIER_TEST_FILENAME
    os.chmod(test_path, 0o644)
    test_path.write_text("def test_tampered():\n    assert False\n", encoding="utf-8")

    def _never_called(*_args, **_kwargs):
        raise AssertionError("runner must not be called when the frozen test is tampered")

    with pytest.raises(RuntimeError, match="hash mismatch"):
        score_mutants(load_case("issue-07"), frozen_dir, tmp_path / "ws",
                      Trace(tmp_path / "t.jsonl"), runner=_never_called)


def test_score_written_to_mutation_results_json_with_denominator(tmp_path):
    """mutation_results.json records the denominator next to the score."""
    frozen_dir, _ = _freeze(_test(), tmp_path)
    score_mutants(
        load_case("issue-07"), frozen_dir, tmp_path / "ws",
        Trace(tmp_path / "t.jsonl"),
        runner=_runner(_exec("1 failed in 0.1s", exit_code=1), *(_exec("1 passed") for _ in range(4))),
    )
    doc = json.loads((frozen_dir / MUTATION_RESULTS_FILENAME).read_text(encoding="utf-8"))
    assert doc["denominator"] == 4, (
        "issue-07's m07-2 is flagged in_process_killable: false - a threading.Lock "
        "genuinely fixes the race inside the single process every oracle here runs "
        "in, so no test can kill it and it must not cap the achievable score"
    )
    assert doc["excluded_unkillable"] == ["m07-2"]
    # It is still RUN and reported, never silently dropped from the record.
    assert [r["mutant_id"] for r in doc["results"]] == [
        "m07-1", "m07-2", "m07-3", "m07-4", "m07-5",
    ]
    assert doc["killed"] == 1
    assert doc["score"] == 1 / 4
    assert len(doc["results"]) == 5


# ---------------------------------------------------------------------------
# Behavioral bracket, real sandbox (docker)
# ---------------------------------------------------------------------------


@pytest.mark.docker
def test_weak_test_scores_zero_against_issue07_manifest(tmp_path):
    case = load_case("issue-07")
    weak = VerifierTest(
        case_id="issue-07",
        filename="test_weak.py",
        contents="def test_nothing():\n    assert True\n",
        run_command="pytest test_weak.py",
        invariant="nothing meaningful",
        confidence=Confidence.high,
    )
    frozen_dir, _ = _freeze(weak, tmp_path)
    results = score_mutants(case, frozen_dir, tmp_path / "ws", Trace(tmp_path / "t.jsonl"))
    assert len(results) == 5
    assert all(not r.killed for r in results)
    assert sum(1 for r in results if r.killed) == 0


@pytest.mark.docker
def test_gold_test_scores_high_against_issue07_manifest(tmp_path):
    case = load_case("issue-07")
    gold_file = ROOT / case.gold_tests[0] / "test_concurrent_registration.py"
    gold = VerifierTest(
        case_id="issue-07",
        filename=gold_file.name,
        contents=gold_file.read_text(encoding="utf-8"),
        run_command=f"pytest {gold_file.name}",
        invariant="at most one registration per (user, event)",
        confidence=Confidence.high,
    )
    frozen_dir, _ = _freeze(gold, tmp_path)
    results = score_mutants(case, frozen_dir, tmp_path / "ws", Trace(tmp_path / "t.jsonl"))
    killed = sum(1 for r in results if r.killed)
    assert len(results) == 5
    assert killed >= 4, [r.model_dump() for r in results]
