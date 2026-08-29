"""Module 7: gate + freeze tests.

The gate's validity logic is covered offline by injecting a scripted runner that
returns canned :class:`~splitspec.sandbox.ExecResult` values, so no Docker and no
network are needed for the three discriminating outcomes. Freeze/tamper/load are
pure host-side file logic. One end-to-end test runs the real Docker sandbox so a
hand-written test is graded against the actual buggy code.
"""
from __future__ import annotations

import os

import pytest
import yaml

from splitspec import sandbox
from splitspec.config import ROOT, Provider, Settings
from splitspec.freeze import VERIFIER_TEST_FILENAME, freeze, load_frozen
from splitspec.gate import gate
from splitspec.schemas import Case, Confidence, ValidityGate, VerifierTest
from splitspec.trace import Trace


def _settings(**overrides) -> Settings:
    def _p(role: str) -> Provider:
        return Provider(role=role, base_url=f"http://{role}.test", model="m")

    params: dict = dict(fixer=_p("fixer"), verifier=_p("verifier"), contract=_p("contract"))
    params.update(overrides)
    return Settings(**params)


def load_case(case_id: str) -> Case:
    data = yaml.safe_load((ROOT / "cases" / f"{case_id}.yaml").read_text())
    return Case.model_validate(data)


def _test(case_id: str = "issue-01", contents: str = "def test_x():\n    assert True\n") -> VerifierTest:
    return VerifierTest(
        case_id=case_id,
        filename="test_probe.py",
        contents=contents,
        run_command="pytest test_probe.py",
        invariant="a behavioral invariant",
        assumptions=["auth required"],
        confidence=Confidence.high,
    )


def _exec(stdout: str, stderr: str = "", exit_code: int = 0) -> sandbox.ExecResult:
    return sandbox.ExecResult(
        exit_code=exit_code, stdout=stdout, stderr=stderr, duration_sec=0.1,
    )


def _run(runner_outcomes: list[sandbox.ExecResult], tmp_path) -> ValidityGate:
    """Drive gate() once with a fake runner, returning its ValidityGate."""
    def runner(*_args, **_kwargs):
        return runner_outcomes.pop(0)

    return gate(
        _test(),
        load_case("issue-01"),
        tmp_path,
        Trace(tmp_path / "trace.jsonl"),
        runner=runner,
    )


# --- freeze / load_frozen ------------------------------------------------------


def test_freeze_writes_artifacts_readonly_and_sets_hash(tmp_path):
    frozen = freeze(_test(), tmp_path)
    test_path = tmp_path / VERIFIER_TEST_FILENAME
    meta_path = tmp_path / "verifier_meta.json"
    assert test_path.is_file()
    assert meta_path.is_file()
    assert frozen.frozen_sha256
    # read-only
    assert os.stat(test_path).st_mode & 0o444 == 0o444
    assert os.stat(meta_path).st_mode & 0o444 == 0o444
    # record every schema field in the sidecar
    restored = load_frozen(tmp_path)
    assert restored == frozen
    assert restored.case_id == "issue-01"
    assert restored.filename == "test_probe.py"
    assert restored.confidence == Confidence.high


def test_load_frozen_raises_on_tampering(tmp_path):
    test_path = tmp_path / VERIFIER_TEST_FILENAME
    frozen = freeze(_test(), tmp_path)
    assert frozen.frozen_sha256
    # freeze() chmods to 0o444; restore write so a plain write_text can modify it.
    os.chmod(test_path, 0o644)
    test_path.write_text("def test_x():\n    assert False\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="tampered"):
        load_frozen(tmp_path)


def test_load_frozen_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_frozen(tmp_path)


# --- gate outcome logic (injected runner) --------------------------------------


def test_gate_marks_test_passing_on_bug_as_invalid_with_reason(tmp_path):
    # stdin pytest summary: the test PASSED on buggy code -> 1 passed, 0 failed.
    result = _run([_exec(stdout="1 passed in 0.1s\n")], tmp_path)
    assert isinstance(result, ValidityGate)
    assert result.compiles is True
    assert result.runs is True
    assert result.fails_on_original_bug is False
    assert result.passed is False
    assert "not discriminating" in result.reason


def test_gate_marks_test_failing_on_bug_as_valid(tmp_path):
    result = _run([_exec(stdout="1 failed in 0.1s\n")], tmp_path)
    assert result.compiles is True
    assert result.runs is True
    assert result.fails_on_original_bug is True
    assert result.passed is True
    assert "as expected" in result.reason


def test_gate_assertion_error_stdout_is_a_run_not_a_crash(tmp_path):
    # A real failed test prints an AssertionError: line; that must be treated as the
    # test RUNNING and catching the bug, never as a collection crash (regression for
    # a gate that matched the broad substring "Error:" inside AssertionError:).
    out = (
        "    failures = [r for r in responses if r.status_code == 201]\n"
        "E       AssertionError: BUG DETECTED: 2 successful concurrent registrations, expected 1.\n"
        "test_issue_07_repro.py:26: AssertionError\n"
        "=========================== short test summary info ============================\n"
        "1 failed in 0.06s\n"
    )
    result = _run([_exec(stdout=out)], tmp_path)
    assert result.runs is True
    assert result.fails_on_original_bug is True
    assert result.passed is True


def test_gate_marks_test_that_cannot_import_as_did_not_run_not_valid(tmp_path):
    stderr = "ImportError: No module named 'nope'\n"
    result = _run([_exec(stdout="", stderr=stderr, exit_code=2)], tmp_path)
    assert result.runs is False
    assert result.compiles is False
    assert result.fails_on_original_bug is False
    assert result.passed is False
    assert "did not run" in result.reason
    assert result.reason


def test_gate_marks_test_with_collection_errors_as_did_not_run_not_valid(tmp_path):
    # A test that errors during ERROR collection must not count as catching the bug.
    result = _run([_exec(stdout="3 errors in 0.1s\n")], tmp_path)
    assert result.runs is True  # pytest executed, but nothing failed
    assert result.fails_on_original_bug is False
    assert result.passed is False
    assert "not discriminating" in result.reason


def test_gate_errors_do_not_count_as_catching_bug(tmp_path):
    # 2 errors and 0 failed -> the module errored, no test actually failed on a bug.
    result = _run([_exec(stdout="2 errors in 0.1s\n", exit_code=2)], tmp_path)
    assert result.runs is True
    assert result.fails_on_original_bug is False
    assert result.passed is False


def test_gate_for_case_11_with_no_buggy_variant_skips_pytest(tmp_path):
    case = load_case("issue-11")
    assert case.buggy_files == []
    called = {"n": 0}

    def runner(*_args, **_kwargs):
        called["n"] += 1
        return _exec(stdout="")

    result = gate(_test("issue-11"), case, tmp_path, Trace(tmp_path / "trace.jsonl"), runner=runner)
    assert called["n"] == 0  # no pytest run at all
    assert result.passed is False
    assert result.compiles is None
    assert result.runs is None
    assert result.fails_on_original_bug is None
    assert "no buggy variant" in result.reason


def test_gate_rejects_non_pytest_collectible_filename(tmp_path):
    bad = _test()
    bad = bad.model_copy(update={"filename": "app/utils.py"})
    with pytest.raises(ValueError, match="collectible"):
        gate(bad, load_case("issue-01"), tmp_path, Trace(tmp_path / "trace.jsonl"),
             runner=lambda *a, **k: _exec(""))


# --- end-to-end (real Docker) --------------------------------------------------


@pytest.mark.docker
def test_gate_end_to_end_issue01(tmp_path):
    case = load_case("issue-01")
    # A hand-written test mirroring the gold invariant: empty titles and negative
    # prices are rejected. On the BUGGY code it must fail -> valid gate.
    contents = (
        "from __future__ import annotations\n"
        "\n"
        "async def test_empty_title_rejected(client, auth_headers, tokens):\n"
        "    r = await client.post('/events', headers=auth_headers(tokens['alice']),\n"
        "                          json={'title': '', 'starts_at': '2026-08-01T09:00:00Z',\n"
        "                                'price': '10.00', 'currency': 'USD'})\n"
        "    assert r.status_code == 422\n"
    )
    frozen = _test("issue-01", contents=contents)

    result = gate(frozen, case, tmp_path / "gate", Trace(tmp_path / "trace.jsonl"))
    assert result.runs is True
    assert result.compiles is True
    assert result.fails_on_original_bug is True
    assert result.passed is True
