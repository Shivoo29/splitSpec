"""Neutral judge (Module 8).

Executes, in one fresh workspace with the patch applied, the three test suites in
fixed order: visible tests, then (in splitspec mode, only when a valid frozen
verifier test is supplied) the frozen verifier test, then gold tests LAST in a
separate container invocation with the gold suite mounted read-only at
``/workspace/gold``.

The judge makes no inferences and calls no model. It only records what pytest
reports: commands, exit codes, counts, durations, output tails, and the JUnit XML
paths, as :class:`~splitspec.schemas.TestRun`. Counts always come from the JUnit
XML, never from scraping stdout.

Information boundaries are asserted in code, not left to convention:

- the visible and verifier invocations must NOT receive the gold mount,
- the gold invocation is the only one that does,
- gold results are written inside the judge workspace (itself never an agent
  workspace) and the sandbox trace is written beside it; nothing an agent can read
  ever receives gold output.

Each suite collects only its own files: the visible tests are copied flat into the
workspace root (the fixture's ``pytest.ini`` excludes ``visible_tests/`` from
recursive collection, so the suite copies are the collected ones), the frozen
verifier test is written to the root under its own collectible ``test_*.py`` name,
and gold runs straight off the read-only ``/workspace/gold`` mount.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from splitspec import sandbox
from splitspec.config import GOLD_TESTS_DIR, ROOT
from splitspec.freeze import load_frozen
from splitspec.schemas import Case, Mode, Patch, TestRun
from splitspec.trace import Trace

#: Wall-clock ceiling for each pytest invocation. The concurrency gold suite is the
#: longest (threaded rounds), so this is generous; the gate uses its own constant.
_JUDGE_TIMEOUT_SEC = 300

#: Where pytest's JUnit XML lands inside the workspace; parallel to no agent dir.
_JUNIT_DIR = ".junit"

# Gold tests are mounted at /workspace/gold - inside the judge workspace tree - so
# that pytest's conftest discovery (which walks a collected path's ancestors) finds
# /workspace/conftest.py and its fixtures. A plain /gold target outside the tree would
# not load those fixtures, so any gold suite that depends on them would error instead
# of failing/passing. The judge workspace is ephemeral and never an agent workspace,
# so the gold content living there is safe: no agent ever sees it.
_GOLD_TARGET = "/workspace/gold"


Runner = Callable[..., sandbox.ExecResult]


def _copy_flat(ws: sandbox.Workspace, src: Path) -> list[str]:
    """Copy every ``test_*.py`` under ``src`` flat into the workspace root.

    Returns the copied basenames for the explicit pytest target. Mirrors how the
    case-meta suite runs tests so the fixture's ``visible_tests/`` is never the
    thing being collected.
    """
    names: list[str] = []
    for test_file in sorted(src.glob("test_*.py")):
        dst = ws.path / test_file.name
        dst.write_text(test_file.read_text(encoding="utf-8"), encoding="utf-8")
        names.append(test_file.name)
    return names


def _run_suite(
    ws: sandbox.Workspace,
    label: str,
    targets: list[str],
    timeout: int,
    trace: Trace,
    runner: Runner,
    mounts: dict[Path, str] | None = None,
) -> TestRun:
    """Run one pytest invocation and turn its JUnit XML into a TestRun.

    ``mounts`` is passed through verbatim; it is ``None``/empty for every suite
    except gold, which is the only one that may carry the gold mount.
    """
    (ws.path / _JUNIT_DIR).mkdir(parents=True, exist_ok=True)
    junit = f"/workspace/{_JUNIT_DIR}/{label}.xml"
    command = ["pytest", "-q", "--junitxml=" + junit, *targets]
    result = runner(ws, command, timeout, mounts=mounts)

    junit_host = ws.path / _JUNIT_DIR / f"{label}.xml"
    if junit_host.is_file():
        run = sandbox.parse_junit(junit_host, label)
    else:
        # pytest never reached the reporter (session-level import/collection crash),
        # so there is no JUnit to trust. Record zero counts and a failure.
        run = TestRun(label=label, command=" ".join(command), passed=False)
    run.command = " ".join(command)
    run.duration_sec = round(result.duration_sec, 3)
    run.stdout_tail = (result.stdout or "")[-4000:]
    trace.event(
        "judge", "suite",
        case_id=ws.case_id, label=label, command=run.command,
        exit_code=result.exit_code, passed=run.passed, total=run.total,
        failures=run.failures, errors=run.errors,
        duration_sec=run.duration_sec,
    )
    return run


def judge(
    case: Case,
    patch: Patch,
    frozen_verifier_test: Path | None,
    mode: Mode,
    root: Path,
    trace: Trace,
    *,
    runner: Runner | None = None,
) -> dict[str, TestRun]:
    """Run visible, (verifier), and gold suites in a fresh patched workspace.

    ``runner`` is injectable for offline tests; it must accept
    ``(ws, command, timeout, mounts)`` like :func:`sandbox.run_in_sandbox`.
    ``frozen_verifier_test`` is the artifact directory written by
    :func:`splitspec.freeze.freeze`; the judge re-hashes it via :func:`load_frozen`
    so a tampered test aborts here too. Pass ``None`` (or run in baseline mode) to
    skip the verifier suite.
    """
    runner = runner or sandbox.run_in_sandbox
    runs: dict[str, TestRun] = {}

    # Load (and re-hash) the frozen test up front: a tampered artifact aborts the
    # judge immediately, before any suite runs, rather than mid-stream.
    frozen = (
        load_frozen(frozen_verifier_test)
        if mode == "splitspec" and frozen_verifier_test is not None
        else None
    )

    ws = sandbox.materialize(case, "judge", root)
    try:
        ws.apply_patch(patch.diff)

        # --- visible: no gold mount, before any verifier/gold run -------------
        visible_files = _copy_flat(ws, ROOT / case.visible_tests[0])
        runs["visible"] = _run_suite(
            ws, "visible", visible_files, _JUDGE_TIMEOUT_SEC, trace, runner,
        )

        # --- verifier: splitspec mode + a valid frozen test only --------------
        if frozen is not None:
            (ws.path / frozen.filename).write_text(frozen.contents, encoding="utf-8")
            runs["verifier"] = _run_suite(
                ws, "verifier", [frozen.filename], _JUDGE_TIMEOUT_SEC, trace, runner,
            )
        else:
            trace.event(
                "judge", "verifier_skipped",
                case_id=case.id, mode=mode, reason=(
                    "no_frozen_test" if frozen_verifier_test is None else "baseline_mode"
                ),
            )

        # --- gold LAST, own container, gold mounted read-only -----------------
        gold_mounts = {GOLD_TESTS_DIR / case.id: _GOLD_TARGET}
        runs["gold"] = _run_suite(
            ws, "gold", [_GOLD_TARGET], _JUDGE_TIMEOUT_SEC, trace, runner,
            mounts=gold_mounts,
        )
    finally:
        ws.destroy()

    # The visible and verifier invocations ran with no mounts at all (see the
    # _run_suite calls above); only the gold invocation received the gold mount.
    # The offline tests assert this by capturing the injected runner's arguments.
    return runs
