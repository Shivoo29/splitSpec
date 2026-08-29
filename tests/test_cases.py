"""Module 2 meta-test: prove every seeded case has the expected test behavior.

For each cases/issue-NN.yaml this materializes a throwaway workspace (the clean
EventPulse fixture, optionally with the case's buggy files overlaid), copies in
the case's visible or gold tests, and runs pytest in a subprocess with the same
interpreter. It asserts, per the LLD:

- visible tests pass on the buggy variant,
- gold hidden tests fail on the buggy variant,
- gold hidden tests pass on the clean reference fixture.

Runs are isolated, offline, and deterministic: fixed seeds, a fixed clock, and
no Docker so the plain unit suite can exercise it.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from splitspec.config import ROOT
from splitspec.schemas import Case

FIXTURE = ROOT / "fixtures" / "eventpulse"
CASES = sorted((ROOT / "cases").glob("issue-*.yaml"))
CASE_IDS = [c.stem for c in CASES]


_SUMMARY = re.compile(r"(?:(\d+) failed)?(?:, )?(?:(\d+) passed)?(?:, )?(?:(\d+) error)?")


def _outcome(stdout: str) -> tuple[int, int]:
    """Return (failed, errors) parsed from pytest's summary line."""
    failed = errors = 0
    for line in stdout.splitlines():
        for count, word in re.findall(r"(\d+) (failed|error|errors)", line):
            if word.startswith("error"):
                errors = max(errors, int(count))
            else:
                failed = max(failed, int(count))
    return failed, errors


def load_case(path: Path) -> Case:
    raw = yaml.safe_load(path.read_text())
    return Case.model_validate(raw)


@pytest.mark.parametrize("case_file", CASES, ids=CASE_IDS)
def test_case_yaml_matches_schema_and_points_at_existing_artifacts(case_file):
    case = load_case(case_file)
    for rel in case.buggy_files:
        assert (FIXTURE / "bugs" / case.id / rel).is_file(), rel
    for entry in case.visible_tests:
        assert (ROOT / entry).is_dir(), entry
    for entry in case.gold_tests:
        assert (ROOT / entry).is_dir(), entry
    for entry in case.mutants:
        manifest = ROOT / entry / "manifest.yaml"
        assert manifest.is_file(), entry
        data = yaml.safe_load(manifest.read_text())
        assert data["id"] == case.id
        for mutant in data["mutants"]:
            assert (ROOT / entry / mutant["id"]).is_dir(), mutant["id"]


def _materialize(ws: Path, case: Case, overlay_bug: bool, tests_src: Path) -> Path:
    shutil.copytree(FIXTURE / "app", ws / "app")
    for name in ("seed.py", "conftest.py"):
        shutil.copy2(FIXTURE / name, ws / name)
    (ws / "pytest.ini").write_text(
        "[pytest]\nasyncio_mode = auto\nnorecursedirs = visible_tests\n"
    )
    # A real workspace always contains the repository's own visible tests. Case 10's
    # oracle checks that they were not edited, so they must be present but not
    # collected here - only the suite under test runs.
    for entry in case.visible_tests:
        shutil.copytree(ROOT / entry, ws / entry, dirs_exist_ok=True)
    if overlay_bug:
        for rel in case.buggy_files:
            src = FIXTURE / "bugs" / case.id / rel
            dst = ws / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    for test_file in sorted(tests_src.glob("test_*.py")):
        shutil.copy2(test_file, ws / test_file.name)
    return ws


def _run_pytest(ws: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ws,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.mark.parametrize("case_file", CASES, ids=CASE_IDS)
def test_visible_passes_on_buggy_variant(case_file, tmp_path):
    case = load_case(case_file)
    ws = _materialize(tmp_path / "ws", case, overlay_bug=True, tests_src=ROOT / case.visible_tests[0])
    result = _run_pytest(ws)
    if not case.buggy_files or case.visible_passes_on_bug:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        # The inverted case: a correct visible test that the defect breaks.
        assert result.returncode != 0, "this case's visible test must fail on the bug"
        assert result.stdout + result.stderr


@pytest.mark.parametrize("case_file", CASES, ids=CASE_IDS)
def test_gold_fails_on_buggy_variant(case_file, tmp_path):
    case = load_case(case_file)
    if not case.buggy_files:
        pytest.skip("no buggy variant: this case's oracle asserts nothing changed")
    ws = _materialize(tmp_path / "ws", case, overlay_bug=True, tests_src=ROOT / case.gold_tests[0])
    result = _run_pytest(ws)
    failed, errors = _outcome(result.stdout)
    report = result.stdout + result.stderr
    # A non-zero exit code is not enough: an import error, a syntax error, or a
    # collection crash would satisfy it while proving nothing about the defect.
    assert errors == 0, "gold tests errored instead of failing:\n" + report
    assert failed >= 1, "gold tests must FAIL on the buggy variant:\n" + report
    for bad in ("ImportError", "SyntaxError", "ModuleNotFoundError", "INTERNALERROR"):
        assert bad not in report, f"gold suite did not run cleanly ({bad}):\n" + report


@pytest.mark.parametrize("case_file", CASES, ids=CASE_IDS)
def test_gold_passes_on_clean_fixture(case_file, tmp_path):
    case = load_case(case_file)
    ws = _materialize(tmp_path / "ws", case, overlay_bug=False, tests_src=ROOT / case.gold_tests[0])
    result = _run_pytest(ws)
    assert result.returncode == 0, result.stdout + result.stderr