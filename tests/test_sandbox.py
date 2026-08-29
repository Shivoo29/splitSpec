"""Module 3: sandbox workspace materialization and Docker execution tests.

Most tests require a running Docker daemon and the splitspec-sandbox image, so
they are marked `@pytest.mark.docker` and excluded from the plain unit suite
(see `addopts = "-m 'not docker'"` in pyproject.toml). Run them with
`pytest -q -m docker`. The pure-filesystem tests (patch roundtrip, path escape)
have no `docker` marker and also run in the unit suite.
"""
from __future__ import annotations

import pytest
import yaml

from splitspec import sandbox
from splitspec.config import GOLD_TESTS_DIR, MUTANTS_DIR, ROOT, VISIBLE_TESTS_DIR
from splitspec.schemas import Case

FIXTURE = ROOT / "fixtures" / "eventpulse"


def load_case(case_id: str) -> Case:
    data = yaml.safe_load((ROOT / "cases" / f"{case_id}.yaml").read_text())
    return Case.model_validate(data)


@pytest.mark.docker
def test_materialize_layout_matches_test_cases(tmp_path):
    case = load_case("issue-07")
    ws = sandbox.materialize(case, "judge", tmp_path)
    try:
        assert (ws.path / "app").is_dir()
        assert (ws.path / "seed.py").is_file()
        assert (ws.path / "conftest.py").is_file()
        assert (ws.path / "pytest.ini").read_text() == sandbox.PYTEST_INI
        # visible tests present, and the seeded defect applied
        assert (ws.path / "visible_tests" / "issue-07" / "test_registrations.py").is_file()
    finally:
        ws.destroy()


@pytest.mark.docker
def test_visible_tests_pass_on_buggy_variant(tmp_path):
    case = load_case("issue-07")
    ws = sandbox.materialize(case, "judge", tmp_path)
    try:
        ws.add_tests(VISIBLE_TESTS_DIR / "issue-07", ".")
        res = sandbox.run_in_sandbox(
            ws,
            # -p no:cacheprovider: the container runs as root; don't leave a
            # root-owned .pytest_cache behind in the workspace.
            ["pytest", "-q", "-p", "no:cacheprovider", "--junitxml=/workspace/visible.xml"],
            timeout=240,
        )
        assert res.exit_code == 0, res.stdout + res.stderr
        run = sandbox.parse_junit(ws.path / "visible.xml", "visible")
        assert run.passed and run.total > 0, (run.total, run.failures, run.errors)
    finally:
        ws.destroy()


@pytest.mark.docker
def test_gold_tests_fail_on_bug_with_real_assertions_and_no_collection_errors(tmp_path):
    case = load_case("issue-07")
    ws = sandbox.materialize(case, "judge", tmp_path)
    try:
        gold = GOLD_TESTS_DIR / "issue-07"
        res = sandbox.run_in_sandbox(
            ws,
            # -p no:cacheprovider: never write .pytest_cache into the read-only /gold mount
            ["pytest", "-q", "-p", "no:cacheprovider", "--junitxml=/workspace/gold.xml", "/gold"],
            timeout=300,
            mounts={gold: "/gold"},
        )
        run = sandbox.parse_junit(ws.path / "gold.xml", "gold")
        # The bug must fail with real assertion failures, never a collection or
        # import error (which would prove nothing about the defect).
        assert run.errors == 0, res.stdout + res.stderr
        assert run.failures >= 1, f"gold tests must fail on the bug:\n{res.stdout}"
        assert run.total > 0
        for bad in ("ImportError", "SyntaxError", "ModuleNotFoundError", "INTERNALERROR"):
            assert bad not in res.stdout + res.stderr, f"gold suite did not run cleanly ({bad})"
    finally:
        ws.destroy()


@pytest.mark.docker
def test_case_with_empty_buggy_files_materializes_cleanly(tmp_path):
    case = load_case("issue-11")
    ws = sandbox.materialize(case, "fixer", tmp_path)
    try:
        assert ws.path.is_dir()
        # nothing buggy was overlaid; a clean, untouched workspace diffs empty
        assert ws.snapshot_diff() == ""
    finally:
        ws.destroy()


@pytest.mark.docker
def test_mutant_overlay_can_change_visible_tests(tmp_path):
    case = load_case("issue-12")
    ws = sandbox.materialize(case, "mutation", tmp_path)
    try:
        # before: the visible suite exists with real tests
        visible = ws.path / "visible_tests" / "issue-12" / "test_events.py"
        assert visible.is_file()

        ws.apply_overlay(MUTANTS_DIR / "issue-12" / "m04-follows-the-injection")

        # m04 models an agent deleting the visible suite; the files are gone
        assert not visible.exists()
        assert not (ws.path / "visible_tests" / "issue-12").exists()
    finally:
        ws.destroy()


@pytest.mark.docker
def test_network_call_inside_sandbox_fails(tmp_path):
    case = load_case("issue-07")
    ws = sandbox.materialize(case, "judge", tmp_path)
    try:
        res = sandbox.run_in_sandbox(
            ws,
            ["python", "-c",
             "import urllib.request; urllib.request.urlopen('http://example.com', timeout=5)"],
            timeout=60,
        )
        assert res.exit_code != 0, "network is disabled; this call must fail"
    finally:
        ws.destroy()


@pytest.mark.docker
def test_snapshot_diff_picks_up_edit_and_is_empty_when_untouched(tmp_path):
    case = load_case("issue-07")
    ws = sandbox.materialize(case, "fixer", tmp_path)
    try:
        assert ws.snapshot_diff() == ""

        target = ws.path / "app" / "routes" / "events.py"
        target.write_text(target.read_text() + "\n# a marker edit\n")
        diff = ws.snapshot_diff()
        assert "app/routes/events.py" in diff
        assert "# a marker edit" in diff
    finally:
        ws.destroy()


@pytest.mark.docker
def test_two_materializations_of_same_case_are_identical(tmp_path):
    case = load_case("issue-07")
    a = sandbox.materialize(case, "judge", tmp_path)
    b = sandbox.materialize(case, "judge", tmp_path)
    try:
        def tree(ws):
            files = (p for p in ws.path.rglob("*") if p.is_file())
            return {p.relative_to(ws.path).as_posix(): p.read_bytes() for p in files}

        ta, tb = tree(a), tree(b)
        assert set(ta) == set(tb), "file sets differ between two materializations"
        for rel in ta:
            assert ta[rel] == tb[rel], f"content differs for {rel}"
    finally:
        a.destroy()
        b.destroy()


def test_path_escaping_workspace_root_is_refused(tmp_path):
    case = load_case("issue-07")
    ws = sandbox.materialize(case, "fixer", tmp_path)
    try:
        escaping = (
            "--- a/../../../etc/pwned\n"
            "+++ b/../../../etc/pwned\n"
            "@@ -0,0 +1 @@\n"
            "+owned\n"
        )
        with pytest.raises(sandbox.PathEscape):
            ws.apply_patch(escaping)
    finally:
        ws.destroy()


def test_apply_patch_roundtrips_an_edit(tmp_path):
    """A snapshot_diff must reproduce itself when applied to a fresh workspace."""
    case = load_case("issue-01")
    a = sandbox.materialize(case, "fixer", tmp_path)
    b = sandbox.materialize(case, "fixer", tmp_path)
    try:
        f = a.path / "app" / "routes" / "events.py"
        f.write_text(f.read_text().replace("def list_events", "def list_events  # edited"))
        diff = a.snapshot_diff()
        assert "app/routes/events.py" in diff

        b.apply_patch(diff)
        assert "def list_events  # edited" in (b.path / "app" / "routes" / "events.py").read_text()
        # the edit is fully reproducible: re-diffing b shows the same logical change
        assert "def list_events  # edited" in b.snapshot_diff()
    finally:
        a.destroy()
        b.destroy()


def test_apply_patch_multi_file_diff_does_not_corrupt_prior_file(tmp_path):
    """Regression: a later file's `--- a/<rel>` header (which follows the previous
    file's final hunk and starts with a hyphen) must not be parsed as a removal op
    on that previous file, or its trailing line gets silently dropped.

    issue-07's reference fix spans two files; applying the whole diff to a fresh
    buggy workspace must reproduce the clean reference verbatim.
    """
    import shutil

    case = load_case("issue-07")
    src = sandbox.materialize(case, "src", tmp_path)
    fresh = sandbox.materialize(case, "fresh", tmp_path)
    try:
        # Build the buggy -> clean reference diff across both buggy files.
        for rel in case.buggy_files:
            shutil.copy2(FIXTURE / rel, src.path / rel)
        diff = src.snapshot_diff()

        fresh.apply_patch(diff)
        for rel in case.buggy_files:
            assert (fresh.path / rel).read_text() == (FIXTURE / rel).read_text(), rel
        # nothing outside the changed files leaked into the patch
        assert "app/models.py" in diff and "app/routes/registrations.py" in diff
    finally:
        src.destroy()
        fresh.destroy()


def test_apply_patch_creates_a_new_file(tmp_path):
    case = load_case("issue-01")
    ws = sandbox.materialize(case, "fixer", tmp_path)
    try:
        ws.path.joinpath("app", "new_module.py").write_text("X = 1\n")
        diff = ws.snapshot_diff()
        fresh = sandbox.materialize(case, "fixer", tmp_path)
        fresh.apply_patch(diff)
        assert (fresh.path / "app" / "new_module.py").read_text() == "X = 1\n"
        fresh.destroy()
    finally:
        ws.destroy()


@pytest.mark.docker
def test_timeout_returns_a_result_rather_than_raising(tmp_path):
    case = load_case("issue-07")
    ws = sandbox.materialize(case, "judge", tmp_path)
    try:
        res = sandbox.run_in_sandbox(
            ws, ["python", "-c", "import time; time.sleep(30)"], timeout=2
        )
        assert res.exit_code != 0
        assert res.duration_sec < 15
    finally:
        ws.destroy()
