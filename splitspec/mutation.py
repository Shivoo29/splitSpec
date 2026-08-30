"""Mutation evaluator (Module 10).

Scores a frozen verifier test's discriminatory power: for every mutant in the
case's manifest, run the test in a fresh workspace against a workspace carrying
that mutant, and record ``killed = the test FAILED on this mutant``.

These are the module-level ground rules that shape the implementation:

- **The manifest is the root of truth, never a glob.** ``manifest.yaml`` itself
  matches a bare ``m*`` glob and every case directory also holds files whose names
  start with ``m`` (e.g. ``m07-1``). Iterating ``manifest.yaml``'s ``mutants``
  list is the only correct enumeration; anything else silently miscounts.
- **killed is about the test's discrimination, not the container's exit code.** A
  mutant that makes the test crash on import has *not* been caught by the test's
  discrimination, so it is ``killed=False`` with a detail saying the test did not
  run — a finding deliberately distinct from "ran and passed". The single outcome
  parser lives in :mod:`splitspec.gate` (``_outcome``/``_did_run``); this module
  reuses it rather than re-implement a second one.
- One container per mutant, same ``--network none`` sandbox constraints as the
  judge and gate. Content-free runner is injected so all the decision logic is
  covered offline; only the real Docker sandbox ships the two scoring tests.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import yaml

from splitspec import sandbox
from splitspec.config import MUTANTS_DIR
from splitspec.freeze import load_frozen
from splitspec.gate import _did_run, _outcome, _safe_test_name
from splitspec.schemas import Case, MutationResult, VerifierTest
from splitspec.trace import Trace

#: Wall-clock ceiling for one mutant's pytest run. The concurrency mutant suites
#: are the slowest; keep it in line with the gate's constant (120s).
_MUTATION_TIMEOUT_SEC = 120

#: The §13 artifact name; written inside the frozen-test artifact directory.
MUTATION_RESULTS_FILENAME = "mutation_results.json"


def _load_manifest(case_id: str) -> list[dict]:
    """Read ``mutant_patches/<case>/manifest.yaml`` and return its mutant entries.

    Returns the ``mutants`` entries in manifest order, which is the deterministic
    case-wide iteration order (ground rule 6). A bare directory glob is never used,
    precisely because it would pick up ``manifest.yaml`` itself.
    """
    manifest_path = MUTANTS_DIR / case_id / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("mutants"), list):
        raise ValueError(f"malformed mutation manifest: {manifest_path}")
    return [dict(entry) for entry in data["mutants"]]


def _evaluate_mutant(
    frozen: VerifierTest,
    case: Case,
    overlay: Path,
    root: Path,
    runner: Callable[..., sandbox.ExecResult],
) -> tuple[bool, str]:
    """Run the frozen test against one mutant in a fresh workspace.

    Returns ``(killed, detail)`` where ``detail`` distinguishes the three possible
    findings: the test failed on the mutant (killed), the test passed on the mutant
    (not killed), or the test never ran because the mutant broke collection or
    import (also not killed, but for a different reason Module 11 reports apart).
    """
    ws = sandbox.materialize(case, "mutation", root)
    try:
        # A fresh workspace carries the seeded bug (materialize applies it); the
        # mutant overlay sits on top. sandbox.apply_overlay honors the `.deleted`
        # marker case 12's m04 uses to delete the visible suite.
        ws.apply_overlay(overlay)

        test_name = _safe_test_name(frozen.filename)
        (ws.path / test_name).write_text(frozen.contents or "", encoding="utf-8")

        result = runner(
            ws,
            ["pytest", "-q", "-p", "no:cacheprovider", test_name],
            _MUTATION_TIMEOUT_SEC,
        )
        stdout, stderr = result.stdout or "", result.stderr or ""

        if not _did_run(stdout, stderr):
            # The mutant broke import/collection, so the test never ran. That is
            # not the test having "caught" the bug; record it as a distinct finding.
            return (
                False,
                "test did not run on this mutant (import/collection failure), "
                "so it was not killed by this test's discrimination",
            )

        failed, errors = _outcome(stdout)
        if failed >= 1 and errors == 0:
            return True, f"test failed on this mutant ({failed} failed, {errors} errors)"
        return False, f"test passed on this mutant ({failed} failed, {errors} errors)"
    finally:
        ws.destroy()


def score_mutants(
    case: Case,
    frozen_test_dir: Path,
    root: Path,
    trace: Trace,
    *,
    runner: Callable[..., sandbox.ExecResult] | None = None,
) -> list[MutationResult]:
    """Score ``case``'s frozen verifier test against every mutant in its manifest.

    ``frozen_test_dir`` is the artifact directory written by ``freeze.freeze()``;
    the test is loaded and re-hashed via :func:`load_frozen`, so a tampered test
    aborts here before any mutant runs. ``root`` names the directory under which
    throwaway mutation workspaces are created. ``runner`` defaults to the real
    Docker runner; unit tests inject a canned stand-in.

    Returns the per-mutant :class:`MutationResult` list (which the orchestrator
    folds into ``RunResult.mutation``) and writes the richer score document
    (score, denominator, per-mutant results) to ``mutation_results.json`` inside
    ``frozen_test_dir``.
    """
    runner = runner or sandbox.run_in_sandbox
    frozen_test_dir = Path(frozen_test_dir)
    root = Path(root)

    frozen = load_frozen(frozen_test_dir)  # hash mismatch aborts the whole run
    mutants = _load_manifest(case.id)

    results: list[MutationResult] = []
    for entry in mutants:
        mutant_id = entry["id"]
        overlay = MUTANTS_DIR / case.id / mutant_id
        if not overlay.is_dir():
            raise FileNotFoundError(
                f"mutant overlay missing for {case.id}: {overlay}"
            )
        killed, detail = _evaluate_mutant(frozen, case, overlay, root, runner)
        results.append(
            MutationResult(
                mutant_id=mutant_id,
                description=entry.get("description", ""),
                killed=killed,
                detail=detail,
                scored=entry.get("in_process_killable") is not False,
            )
        )

    # A mutant flagged in_process_killable: false is one NO test in this harness can
    # kill - issue-07's m07-2 adds a threading.Lock, which genuinely serializes the
    # race inside the single process every oracle here runs in. Counting it would cap
    # every achievable score below 1.0 and make a perfect test look like it missed
    # one, so it is run and reported but kept out of the denominator.
    excluded = {r.mutant_id for r in results if not r.scored}
    scored = [r for r in results if r.scored]

    killed_count = sum(1 for r in scored if r.killed)
    denominator = len(scored)
    # Missing data is None, never 0: nothing scorable means no measurable score.
    score = killed_count / denominator if denominator else None

    _write_results(
        frozen_test_dir, score, killed_count, denominator, results, sorted(excluded)
    )

    trace.event(
        "mutation", "score",
        case_id=case.id,
        test_filename=_safe_test_name(frozen.filename),
        killed=killed_count,
        denominator=denominator,
        score=score,
        mutants=[r.mutant_id for r in results],
        excluded_unkillable=sorted(excluded),
    )
    return results


def _write_results(
    frozen_test_dir: Path,
    score: float | None,
    killed: int,
    denominator: int,
    results: list[MutationResult],
    excluded: list[str],
) -> None:
    """Persist ``mutation_results.json`` (PROJECT.md §13) with score + denominator."""
    doc = {
        "score": score,
        "killed": killed,
        "denominator": denominator,
        # Reported, never silently dropped: a reader must be able to see which
        # mutants the score could not have been asked to kill, and why.
        "excluded_unkillable": excluded,
        "results": [r.model_dump(mode="json") for r in results],
    }
    path = frozen_test_dir / MUTATION_RESULTS_FILENAME
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
