"""Docker-backed sandbox runner and workspace materializer (Module 3).

A :class:`Workspace` is an isolated, deterministic copy of the EventPulse fixture
at a known state, laid out identically to ``tests/test_cases.py`` so every
existing case keeps behaving:

- ``app/``             copied from ``fixtures/eventpulse/app``
- ``seed.py``, ``conftest.py`` and a ``pytest.ini`` with ``asyncio_mode = auto``
- ``visible_tests/<case-id>/`` present but excluded from collection
- the suite under test copied flat into the workspace root

Everything agent-authored executes inside a Docker container with
``--network none``; the caller of :func:`run_in_sandbox` decides whether the gold
tests are mounted (read-only at ``/gold``) — per the LLD only the judge and
mutation modules ever do.
"""
from __future__ import annotations

import difflib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from splitspec.config import ROOT, Settings
from splitspec.schemas import Case, TestRun
from splitspec.trace import Trace

FIXTURE = ROOT / "fixtures" / "eventpulse"
PYTEST_INI = "[pytest]\nasyncio_mode = auto\nnorecursedirs = visible_tests\n"

# Files and directories never part of the diff/state: build artifacts and
# runtime databases are incidental, not a fixer's or a mutant's change.
# Run artifacts, not anyone's change: a JUnit report or a stray trace must never
# appear in a patch, or the judge would apply the fixer's own test output.
_IGNORED_BASENAMES = {"__pycache__", ".pytest_cache", "sandbox.jsonl"}
_IGNORED_SUFFIXES = {".pyc", ".db", ".sqlite3", ".xml"}

_TIMEOUT_EXIT = 124  # mirrors the `timeout(1)` convention; a timeout is a result, not a crash


def _walk_state(root: Path) -> dict[str, bytes]:
    """Map every tracked file under ``root`` to its bytes, sorted for determinism."""
    state: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.name in _IGNORED_BASENAMES or any(p.name in _IGNORED_BASENAMES for p in path.parents):
            continue
        if path.suffix in _IGNORED_SUFFIXES:
            continue
        if not path.is_file():
            continue
        state[path.relative_to(root).as_posix()] = path.read_bytes()
    return state


def _unified(rel: str, old: bytes | None, new: bytes | None) -> str:
    def _lines(data: bytes | None) -> list[str]:
        return [] if data is None else data.decode("utf-8", errors="replace").splitlines(keepends=True)

    diff = difflib.unified_diff(
        _lines(old),
        _lines(new),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    )
    return "".join(diff)


@dataclass
class ExecResult:
    """Outcome of one sandboxed command."""

    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    junit_xml_path: str | None = None


class PathEscape(RuntimeError):
    """A path attempted to resolve outside the workspace root."""


def _guard(root: Path, dst: Path) -> Path:
    """Refuse a destination that resolves outside ``root``."""
    try:
        resolved = dst.resolve(strict=False)
    except OSError as exc:  # pragma: no cover - defensive
        raise PathEscape(str(dst)) from exc
    root_resolved = root.resolve()
    if not (resolved == root_resolved or root_resolved in resolved.parents):
        raise PathEscape(str(dst))
    return resolved


class Workspace:
    """A materialized, isolated copy of the fixture at a known state."""

    def __init__(self, path: Path, case_id: str, role: str, case: Case) -> None:
        self.path = Path(path)
        self.case_id = case_id
        self.role = role
        self._case = case
        # Baseline captured once, right after materialization (bug applied), so
        # snapshot_diff() reports exactly what changed since then — a fixer's
        # net patch, never the seeded defect.
        self._baseline = _walk_state(self.path)

    # -- materialization helpers -------------------------------------------------

    @staticmethod
    def _overlay(root: Path, src: Path) -> None:
        """Copy the tree ``src`` onto ``root``, sorted, honoring `.deleted` markers.

        A lone `.<deleted>` marker inside a source directory means the matching
        workspace directory must be removed (mutant m04 of case 12 uses this to
        model an agent deleting the visible test suite).
        """
        src_root = Path(src)
        for item in sorted(src_root.rglob("*")):
            rel = item.relative_to(src_root)
            dst = root / rel
            _guard(root, dst)
            if item.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            elif item.name == ".deleted":
                target = root / rel.parent
                if target.is_dir():
                    shutil.rmtree(target)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)

    def apply_overlay(self, src: Path) -> None:
        """Overlay a source tree (a mutant patch) onto the workspace."""
        self._overlay(self.path, src)

    def apply_bug(self) -> None:
        """Overlay the case's seeded buggy files. Empty ``buggy_files`` is a no-op."""
        bug_dir = FIXTURE / "bugs" / self.case_id
        if bug_dir.is_dir():
            self._overlay(self.path, bug_dir)
        elif self._case.buggy_files:
            raise FileNotFoundError(f"bug overlay dir missing for {self.case_id}: {bug_dir}")

    def add_tests(self, src: Path, dest_rel: str) -> None:
        """Copy the ``test_*.py`` files from ``src`` flat into ``root/dest_rel``."""
        dst = _guard(self.path, self.path / dest_rel)
        dst.mkdir(parents=True, exist_ok=True)
        for test_file in sorted(Path(src).glob("test_*.py")):
            shutil.copy2(test_file, dst / test_file.name)

    def apply_patch(self, diff: str) -> None:
        """Apply a unified diff to the workspace. Any escaping path is refused."""
        for rel, hunks in _parse_diff(diff):
            target = _guard(self.path, (self.path / rel).resolve(strict=False))
            if target.exists():
                _apply_hunks(target, hunks)
            else:
                # A brand-new file: keep only the added lines from every hunk.
                target.parent.mkdir(parents=True, exist_ok=True)
                added = [body + "\n" for _, hunk in hunks for op, body in hunk if op == "+"]
                target.write_text("".join(added), encoding="utf-8")

    def baseline_files(self) -> set[str]:
        """Paths present when the workspace was materialized (after the bug overlay).

        Lets a caller tell a modified file from a newly created one.
        """
        return set(self._baseline)

    def snapshot_diff(self) -> str:
        """A unified diff of the workspace vs its as-materialized state."""
        current = _walk_state(self.path)
        rels = sorted(set(self._baseline) | set(current))
        return "".join(_unified(r, self._baseline.get(r), current.get(r)) for r in rels)

    def destroy(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)


# -- module-level API ------------------------------------------------------------


def materialize(case: Case, role: str, root: Path) -> Workspace:
    """Create a fresh workspace for ``case`` on disk under ``root``.

    The workspace always carries the seeded defect (``case.buggy_files``, empty
    for case 11) plus the case's visible tests, laid out exactly as
    ``tests/test_cases.py`` expects. ``role`` names the workspace directory.
    """
    ws_dir = root / f"{case.id}-{role}"
    if ws_dir.exists():
        shutil.rmtree(ws_dir)
    ws_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(FIXTURE / "app", ws_dir / "app")
    for name in ("seed.py", "conftest.py"):
        shutil.copy2(FIXTURE / name, ws_dir / name)
    (ws_dir / "pytest.ini").write_text(PYTEST_INI)
    for entry in case.visible_tests:
        shutil.copytree(ROOT / entry, ws_dir / entry, dirs_exist_ok=True)

    ws = Workspace(ws_dir, case.id, role, case)
    ws.apply_bug()
    # Re-baseline after the defect is applied so snapshot_diff() reports only
    # changes since the buggy reference state — never the seeded bug itself.
    ws._baseline = _walk_state(ws.path)
    return ws


def run_in_sandbox(
    ws: Workspace,
    command: list[str],
    timeout: int,
    mounts: dict[Path, str] | None = None,
) -> ExecResult:
    """Run ``command`` in the sandbox container over ``ws.path`` mounted at /workspace.

    ``mounts`` maps host paths to container paths (e.g. the gold tests to a
    read-only ``/gold``); per the LLD only the judge and mutation modules pass it.
    A wall-clock timeout is reported as a result, never raised. Every invocation
    is written to the workspace's trace.
    """
    settings = Settings.from_env()
    # A unique container name lets us force-kill the actual container on timeout
    # (`--rm` only triggers when the docker client survives, which it may not).
    name = f"splitspec-{ws.case_id}-{os.getpid()}-{time.monotonic_ns()}"
    argv = [
        "docker", "run", "--rm",
        "--name", name,
        "--network", "none",
        "--memory", "2g", "--pids-limit", "256",
        # Run as the host user so the container never leaves root-owned files in
        # the bind-mounted workspace that the host user cannot delete.
        "-u", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{ws.path}:/workspace",
        "-w", "/workspace",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "PYTHONUNBUFFERED=1",
        # Make the fixture importable (`app`, `seed`) no matter where pytest
        # collects tests from — including /gold, whose dir is otherwise the only
        # sys.path entry.
        "-e", "PYTHONPATH=/workspace",
    ]
    for host_path, container_path in (mounts or {}).items():
        argv += ["-v", f"{Path(host_path).resolve()}:{container_path}:ro"]
    argv += [settings.sandbox_image]
    argv += list(command)

    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        exit_code: int | None = proc.returncode
        stdout, stderr = proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        exit_code = _TIMEOUT_EXIT
        stdout = (_bytes_text(exc.stdout))
        stderr = (_bytes_text(exc.stderr))
        # The docker client was killed on the timeout; kill the live container too.
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
        )
    duration = time.monotonic() - started

    junit_xml_path = _junit_host_path(ws, command)

    _trace_event(ws, argv, exit_code, duration, stdout, stderr)
    return ExecResult(
        exit_code=exit_code, stdout=stdout, stderr=stderr,
        duration_sec=duration, junit_xml_path=junit_xml_path,
    )


def _bytes_text(data) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _junit_host_path(ws: Workspace, command: list[str]) -> str | None:
    for arg in command:
        if arg.startswith("--junitxml="):
            container = arg.split("=", 1)[1]
            if container.startswith("/workspace/"):
                return str(ws.path / container.removeprefix("/workspace/"))
    return None


def _trace_event(ws, argv, exit_code, duration, stdout, stderr) -> None:
    # Beside the workspace, never inside it. A trace written into the tree lands in
    # every snapshot_diff (so the fixer's patch carries its own exec log), and in a
    # judge workspace it would hold gold-test output where an agent could read it.
    trace = Trace(ws.path.parent / f"{ws.path.name}.sandbox.jsonl")
    tail = (stdout + "\n" + stderr).strip().splitlines()[-40:]
    trace.event(
        "sandbox",
        "exec",
        argv=argv,
        exit_code=exit_code,
        duration_sec=round(duration, 3),
        stdout_tail="\n".join(tail),
    )


def parse_junit(path: Path, label: str) -> TestRun:
    """Turn a JUnit XML file into a :class:`schemas.TestRun`.

    Counts come from the XML attributes, never from scraping stdout. pytest's
    single-suite file wraps a `<testsuite>` in a `<testsuites>` root, so walk to
    the first element that actually carries the counters.
    """
    root = ElementTree.parse(path).getroot()
    suite = root if root.tag == "testsuite" else next(
        (child for child in root.iter("testsuite")), root
    )
    total = int(suite.get("tests", 0) or 0)
    failures = int(suite.get("failures", 0) or 0)
    errors = int(suite.get("errors", 0) or 0)
    return TestRun(
        label=label,
        command="",
        passed=failures == 0 and errors == 0,
        total=total,
        failures=failures,
        errors=errors,
        junit_xml_path=str(path),
    )


# -- unified-diff parsing --------------------------------------------------------


def _parse_diff(diff: str) -> list[tuple[str, list[tuple[int, list[tuple[str, str]]]]]]:
    """Parse ``diff`` into ``[(relpath, [(old_start, [(op, text), ...]), ...])]``.

    Handles the subset our ``snapshot_diff`` produces: `+++ b/<rel>` file
    headers, `@@ -a,b +c,d @@` hunk headers, and ` ` (context), `+`, `-` lines.
    A `--- a/<rel>` from-header is a file separator, not a removal: it is the
    first line of every file's section and follows the previous file's final
    hunk, so it must never be captured as a `-` op (it starts with a hyphen).
    """
    files: list[tuple[str, list[tuple[int, list[tuple[str, str]]]]]] = []
    file_i = -1
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append((line.removeprefix("+++ b/"), []))
            file_i = len(files) - 1
        elif line.startswith(("@@ ", "--- a/")) and file_i >= 0:
            if line.startswith("@@ "):
                files[file_i][1].append((_hunk_start(line), []))
        elif file_i >= 0 and files[file_i][1] and line[:1] in "+- ":
            files[file_i][1][-1][1].append((line[:1], line[1:]))
    return files


def _hunk_start(line: str) -> int:
    try:
        marker = line.split(" ", 2)[1]
        return abs(int(marker.split(",")[0].removeprefix("+")))
    except (IndexError, ValueError):
        return 0


def _apply_hunks(target: Path, hunks: list[tuple[int, list[tuple[str, str]]]]) -> None:
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    idx = 0
    for start, hunk in hunks:
        while idx < max(0, start - 1) and idx < len(lines):
            out.append(lines[idx])
            idx += 1
        for op, body in hunk:
            if op == "-":
                idx += 1
            elif op == "+":
                out.append(body + "\n")
            else:  # context
                if idx < len(lines):
                    out.append(lines[idx])
                idx += 1
    out.extend(lines[idx:])
    target.write_text("".join(out), encoding="utf-8")
