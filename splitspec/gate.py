"""Validity gate (Module 7).

:func:`gate` decides whether a frozen :class:`~splitspec.schemas.VerifierTest` has
earned the right to grade a patch: it runs the test against the **original buggy
code** in a fresh sandbox workspace and reports whether the test actually catches
the bug. A test that passes on buggy code is invalid for grading — it never would
have caught a shallow fix — and that is a real outcome that feeds the validity-rate
metric, so it is recorded with a ``reason`` instead of being dropped.

The gate is run by the orchestrator and makes no model calls. The runner is
injectable so the validity logic is fully covered by the offline unit suite while
the real Docker sandbox is exercised by a single ``@pytest.mark.docker`` test.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from splitspec import sandbox
from splitspec.schemas import Case, ValidityGate, VerifierTest
from splitspec.trace import Trace

#: Wall-clock ceiling for the gate's own sandbox run. The gate signature has no
#: Settings, so the timeout lives here as a module constant.
_GATE_TIMEOUT_SEC = 120

#: pytest's summary line is the source of truth; the process exit code is not
#: (pytest returns 5 for "no tests collected", 1 for failures, 2 for errors, and
#: these can't be told apart from a crash). Parse outcome from stdout only.
_OUTCOME = re.compile(r"(\d+) (failed|error|errors)")

#: Any summary line (pass or fail) proves pytest reached its reporter. Absent a
#: crash marker, this distinguishes "the test ran" from "it never collected".
_SUMMARY = re.compile(r"(\d+) (passed|failed|error|errors|skipped|deselected)")

#: pytest prints these to stderr/stdout when a test module refuses to import or
#: collect. An import/collection failure means the test never ran, so it can never
#: count as having caught the bug. Note this deliberately does NOT include the bare
#: substring "Error:" — that appears inside AssertionError:/ValueError: lines, which
#: are normal failed-test output and MUST count as the test having run (and failed).
_CRASH_MARKERS = (
    "ImportError",
    "ModuleNotFoundError",
    "SyntaxError",
    "INTERNALERROR",
    "ERROR collecting",
    "errors during collection",
)


def _outcome(stdout: str) -> tuple[int, int]:
    """Return ``(failed, errors)`` parsed from pytest's summary line."""
    failed = errors = 0
    for line in stdout.splitlines():
        for count, word in _OUTCOME.findall(line):
            if word.startswith("error"):
                errors = max(errors, int(count))
            else:
                failed = max(failed, int(count))
    return failed, errors


def _safe_test_name(filename: str) -> str:
    """Return just the basename of the test file so collection is traversal-safe."""
    name = Path(filename).name
    if not name.endswith(".py"):
        raise ValueError(f"verifier test filename must be a .py file: {filename!r}")
    if not (name.startswith("test_") or name.endswith("_test.py")):
        raise ValueError(f"verifier test filename must be pytest-collectible: {filename!r}")
    return name


def _did_run(stdout: str, stderr: str) -> bool:
    """True only if pytest actually executed the test (no import/collection crash)."""
    if any(marker in stdout + stderr for marker in _CRASH_MARKERS):
        return False
    # A summary line means pytest reached the reporting stage.
    return bool(_SUMMARY.search(stdout))


def gate(
    frozen: VerifierTest,
    case: Case,
    root: Path,
    trace: Trace,
    *,
    runner: Callable[..., sandbox.ExecResult] | None = None,
) -> ValidityGate:
    """Run the frozen test against the original buggy code and grade its validity.

    ``root`` names the directory under which the throwaway gate workspace is
    created. ``runner`` defaults to the real Docker runner; unit tests inject a
    scripted stand-in returning canned :class:`sandbox.ExecResult` values.
    """
    runner = runner or sandbox.run_in_sandbox
    test_name = _safe_test_name(frozen.filename)

    # Case 11 has no buggy variant (buggy_files == []). There is nothing for the
    # test to catch, so we record no pytest run and no booleans: missing data is
    # None, never false, per ground rule 8.
    if not case.buggy_files:
        gate_result = ValidityGate(
            compiles=None,
            runs=None,
            fails_on_original_bug=None,
            passed=False,
            reason="no buggy variant: case has no seeded bug for the test to catch",
        )
        trace.event(
            "gate", "validity",
            case_id=case.id,
            test_filename=test_name,
            skipped="no_buggy_variant",
            passed=False,
        )
        return gate_result

    ws = sandbox.materialize(case, "gate", root)
    try:
        test_path = ws.path / test_name
        test_path.write_text(frozen.contents or "", encoding="utf-8")

        result = runner(
            ws,
            ["pytest", "-q", "-p", "no:cacheprovider", test_name],
            _GATE_TIMEOUT_SEC,
        )
        stdout, stderr = result.stdout or "", result.stderr or ""

        runs = _did_run(stdout, stderr)
        # An import/collection failure is a compile+run failure, never a bug catch.
        compiles = runs
        if not runs:
            failed, errors = 0, 0
        else:
            failed, errors = _outcome(stdout)

        fails_on_bug = runs and failed >= 1 and errors == 0
        passed = compiles and runs and fails_on_bug

        if not runs:
            reason = "test did not run (import/collection failure), so it cannot catch the bug"
        elif runs and not fails_on_bug:
            reason = (
                f"test passed on buggy code ({failed} failed, {errors} errors), "
                "so it is not discriminating"
            )
        else:
            reason = f"test failed on the buggy code ({failed} failures) as expected"

        gate_result = ValidityGate(
            compiles=compiles,
            runs=runs,
            fails_on_original_bug=fails_on_bug,
            passed=passed,
            reason=reason,
        )
        trace.event(
            "gate", "validity",
            case_id=case.id,
            test_filename=test_name,
            compiles=compiles,
            runs=runs,
            fails_on_original_bug=fails_on_bug,
            passed=passed,
            reason=reason,
            exit_code=result.exit_code,
        )
        return gate_result
    finally:
        ws.destroy()
