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
    (ws / "pytest.ini").write_text("[pytest]\nasyncio_mode = auto\n")
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
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("case_file", CASES, ids=CASE_IDS)
def test_gold_fails_on_buggy_variant(case_file, tmp_path):
    case = load_case(case_file)
    ws = _materialize(tmp_path / "ws", case, overlay_bug=True, tests_src=ROOT / case.gold_tests[0])
    result = _run_pytest(ws)
    assert result.returncode != 0, "gold tests must fail on the buggy variant:\n" + result.stdout


@pytest.mark.parametrize("case_file", CASES, ids=CASE_IDS)
def test_gold_passes_on_clean_fixture(case_file, tmp_path):
    case = load_case(case_file)
    ws = _materialize(tmp_path / "ws", case, overlay_bug=False, tests_src=ROOT / case.gold_tests[0])
    result = _run_pytest(ws)
    assert result.returncode == 0, result.stdout + result.stderr