"""Module 8: neutral judge tests.

Offline tests inject a fake runner so no Docker and no model are needed to verify
the judge's ordering, counting, and information-boundary behavior. The two
behavioral docker tests exercise the real sandbox over issue-07's buggy code and
over a generated reference fix.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from splitspec import sandbox
from splitspec.config import GOLD_TESTS_DIR, ROOT
from splitspec.freeze import VERIFIER_TEST_FILENAME, freeze
from splitspec.judge import _GOLD_TARGET, judge
from splitspec.schemas import Case, Confidence, Patch, VerifierTest
from splitspec.trace import Trace

FIXTURE = ROOT / "fixtures" / "eventpulse"


def load_case(case_id: str) -> Case:
    data = yaml.safe_load((ROOT / "cases" / f"{case_id}.yaml").read_text())
    return Case.model_validate(data)


# ---------------------------------------------------------------------------
# Fake runner: records (command, mounts) and writes a JUnit file the judge reads.
# ---------------------------------------------------------------------------


def _junit_xml(label: str, tests: int, failures: int = 0, errors: int = 0) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuites><testsuite name="{label}" tests="{tests}" '
        f'failures="{failures}" errors="{errors}"/></testsuites>\n'
    )


class CapturingRunner:
    """A stand-in for sandbox.run_in_sandbox that never touches Docker.

    Writes the JUnit XML file the judge expects for each invocation, then records
    the call. ``spec`` maps a suite label to (tests, failures, errors) counts.
    """

    def __init__(self, spec: dict[str, tuple[int, int, int]] | None = None) -> None:
        self.spec = spec or {}
        self.calls: list[dict] = []
        self.stdout = ""

    def __call__(self, ws, command, timeout, mounts=None):
        junit_arg = next(a for a in command if a.startswith("--junitxml="))
        label = junit_arg.removeprefix("--junitxml=/workspace/.junit/").removesuffix(".xml")
        tests, failures, errors = self.spec.get(label, (1, 0, 0))
        (ws.path / ".junit").mkdir(parents=True, exist_ok=True)
        (ws.path / ".junit" / f"{label}.xml").write_text(
            _junit_xml(label, tests, failures, errors), encoding="utf-8"
        )
        self.calls.append(
            {
                "label": label,
                "command": list(command),
                "timeout": timeout,
                "mounts": dict(mounts) if mounts else {},
            }
        )
        return sandbox.ExecResult(
            exit_code=1 if failures or errors else 0,
            stdout=self.stdout,
            stderr="",
            duration_sec=0.1,
        )


# ---------------------------------------------------------------------------
# Reference-fix patch: the unified diff that turns issue-07's buggy files into
# the clean (fixed) reference, exactly as apply_patch would consume it.
# ---------------------------------------------------------------------------


def _reference_fix_patch(case: Case) -> Patch:
    """Materialize a buggy workspace, overlay the clean files, diff it."""
    ws = sandbox.materialize(case, "reffix", ROOT / ".tmp-judge-ref")
    try:
        for rel in case.buggy_files:
            clean = FIXTURE / rel
            dst = ws.path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(clean, dst)
        return Patch(case_id=case.id, diff=ws.snapshot_diff())
    finally:
        ws.destroy()


def _frozen_valid_test(tmp_path, case_id: str = "issue-07") -> Path:
    """Freeze a verifier test that passes on the fixed code and return its dir."""
    contents = (
        "from __future__ import annotations\n"
        "\n"
        "async def test_duplicate_registration_rejected(client, auth_headers, tokens):\n"
        "    await client.post('/registrations', headers=auth_headers(tokens['dana']),\n"
        "                      json={'event_id': 1})\n"
        "    r = await client.post('/registrations', headers=auth_headers(tokens['dana']),\n"
        "                          json={'event_id': 1})\n"
        "    assert r.status_code == 409\n"
    )
    test = VerifierTest(
        case_id=case_id,
        filename="test_judge_probe.py",
        contents=contents,
        run_command="pytest test_judge_probe.py",
        invariant="at most one registration per (user, event)",
        confidence=Confidence.high,
    )
    freeze(test, tmp_path / "frozen")
    return tmp_path / "frozen"


# ---------------------------------------------------------------------------


def test_judge_runs_visible_then_gold_with_no_gold_mount_on_visible(tmp_path):
    case = load_case("issue-07")
    runner = CapturingRunner(spec={"visible": (2, 0, 0), "gold": (1, 1, 0)})
    runs = judge(
        case,
        Patch(case_id=case.id, diff=""),
        None,
        "baseline",
        tmp_path / "root",
        Trace(tmp_path / "trace.jsonl"),
        runner=runner,
    )
    assert "visible" in runs and "gold" in runs
    assert "verifier" not in runs
    # gold runs last
    labels = [c["label"] for c in runner.calls]
    assert labels == ["visible", "gold"], labels
    # visible invocation carried no /gold mount and no /gold in its command
    vis = runner.calls[0]
    assert "/gold" not in vis["mounts"].values()
    assert all("/gold" not in tok for tok in vis["command"])
    # gold invocation received the gold mount (read-only, under the workspace so the
    # conftest fixtures load) and targets it
    gold = runner.calls[1]
    assert gold["mounts"] == {GOLD_TESTS_DIR / case.id: _GOLD_TARGET}, gold["mounts"]
    assert any(_GOLD_TARGET in tok for tok in gold["command"])


def test_gold_mount_only_on_gold_invocation(tmp_path):
    case = load_case("issue-07")
    runner = CapturingRunner(spec={"visible": (1, 0, 0), "verifier": (1, 0, 0), "gold": (1, 0, 0)})
    frozen = _frozen_valid_test(tmp_path)
    judge(
        case,
        Patch(case_id=case.id, diff=""),
        frozen,
        "splitspec",
        tmp_path / "root",
        Trace(tmp_path / "trace.jsonl"),
        runner=runner,
    )
    for call in runner.calls:
        if call["label"] == "gold":
            assert call["mounts"] == {GOLD_TESTS_DIR / case.id: _GOLD_TARGET}, call["mounts"]
        else:
            assert call["mounts"] == {}, f"{call['label']} must have no gold mount"
            assert all(_GOLD_TARGET not in tok for tok in call["command"])


def test_counts_come_from_junit_not_stdout(tmp_path):
    case = load_case("issue-07")
    runner = CapturingRunner(spec={"visible": (3, 1, 0), "gold": (4, 0, 0)})
    # Make the fake runner's stdout claim wildly different counts; the judge must
    # ignore stdout entirely and trust only the JUnit XML.
    runner.stdout = "\n".join([f"{n} passed" for n in (1, 2, 3, 4, 5)])
    runs = judge(
        case,
        Patch(case_id=case.id, diff=""),
        None,
        "baseline",
        tmp_path / "root",
        Trace(tmp_path / "trace.jsonl"),
        runner=runner,
    )
    assert runs["visible"].total == 3
    assert runs["visible"].failures == 1
    assert runs["visible"].passed is False
    assert runs["gold"].total == 4
    assert runs["gold"].passed is True


def test_invalid_gated_verifier_test_is_skipped_not_run(tmp_path):
    """frozen_verifier_test=None (the caller only passes a VALID gated test) must
    skip the verifier suite entirely: no verifier invocation, no verifier TestRun."""
    case = load_case("issue-07")
    runner = CapturingRunner(spec={"visible": (1, 0, 0), "gold": (1, 0, 0)})
    runs = judge(
        case,
        Patch(case_id=case.id, diff=""),
        None,
        "splitspec",
        tmp_path / "root",
        Trace(tmp_path / "trace.jsonl"),
        runner=runner,
    )
    assert "verifier" not in runs
    assert "verifier" not in [c["label"] for c in runner.calls]


def test_baseline_mode_skips_verifier_even_if_frozen_test_supplied(tmp_path):
    case = load_case("issue-07")
    runner = CapturingRunner(spec={"visible": (1, 0, 0), "gold": (1, 0, 0)})
    frozen = _frozen_valid_test(tmp_path)
    runs = judge(
        case,
        Patch(case_id=case.id, diff=""),
        frozen,
        "baseline",
        tmp_path / "root",
        Trace(tmp_path / "trace.jsonl"),
        runner=runner,
    )
    assert "verifier" not in runs
    assert "verifier" not in [c["label"] for c in runner.calls]


def test_tampered_frozen_test_aborts_the_judge(tmp_path):
    case = load_case("issue-07")
    frozen_dir = _frozen_valid_test(tmp_path)
    # Tamper: freeze chmods to 0o444, so restore write first.
    test_path = frozen_dir / VERIFIER_TEST_FILENAME
    import os

    os.chmod(test_path, 0o644)
    test_path.write_text(test_path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    runner = CapturingRunner()
    with pytest.raises(RuntimeError, match="tampered"):
        judge(
            case,
            Patch(case_id=case.id, diff=""),
            frozen_dir,
            "splitspec",
            tmp_path / "root",
            Trace(tmp_path / "trace.jsonl"),
            runner=runner,
        )
    # The judge aborted before running anything (load_frozen raises up front).
    assert runner.calls == []


def test_judge_writes_suite_events_to_trace(tmp_path):
    case = load_case("issue-07")
    runner = CapturingRunner(spec={"visible": (1, 0, 0), "gold": (1, 0, 0)})
    trace = Trace(tmp_path / "trace.jsonl")
    judge(
        case,
        Patch(case_id=case.id, diff=""),
        None,
        "baseline",
        tmp_path / "root",
        trace,
        runner=runner,
    )
    kinds = [e["kind"] for e in trace.read()]
    assert kinds.count("suite") == 2
    assert "verifier_skipped" in kinds


# ---------------------------------------------------------------------------
# Real sandbox: issue-07 behavior
# ---------------------------------------------------------------------------


@pytest.mark.docker
def test_issue07_buggy_code_visible_passes_gold_fails(tmp_path):
    case = load_case("issue-07")
    runs = judge(
        case,
        Patch(case_id=case.id, diff=""),
        None,
        "baseline",
        tmp_path / "root",
        Trace(tmp_path / "trace.jsonl"),
    )
    assert runs["visible"].passed is True, runs["visible"].stdout_tail
    assert runs["gold"].passed is False, runs["gold"].stdout_tail
    assert runs["gold"].failures >= 1


@pytest.mark.docker
def test_issue07_reference_fix_all_three_pass(tmp_path):
    case = load_case("issue-07")
    patch = _reference_fix_patch(case)
    assert patch.diff
    frozen_dir = _frozen_valid_test(tmp_path)
    runs = judge(
        case,
        patch,
        frozen_dir,
        "splitspec",
        tmp_path / "root",
        Trace(tmp_path / "trace.jsonl"),
    )
    for label in ("visible", "verifier", "gold"):
        assert runs[label].passed is True, f"{label}: {runs[label].stdout_tail}"
