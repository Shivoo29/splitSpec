"""Mutation evaluation CLI (Module 10).

`python -m splitspec.mutate --case cases/issue-07.yaml --verifier-test <path> --output <json>`

Scores a frozen verifier test against the case's mutant manifest and writes the
score (with its denominator) plus the per-mutant results to `--output`.

``--verifier-test`` accepts either a frozen artifact directory (the
``verifier_test.py`` + ``verifier_meta.json`` pair written by
:func:`splitspec.freeze.freeze`) or a bare ``.py`` test file (e.g. a gold hidden
test used as a "perfect" test to sanity-check that the manifest is killable); a
bare file is frozen first so every path still flows through
:func:`splitspec.freeze.load_frozen` and its tamper check.

This module is the CLI *edge*: it calls :func:`splitspec.config.load_dotenv` and
nothing else does, so :func:`Settings.from_env` stays hermetic and the unit suite
never reads the developer's real ``.env``.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer
import yaml

from splitspec.config import load_dotenv
from splitspec.freeze import freeze
from splitspec.mutation import MUTATION_RESULTS_FILENAME, score_mutants
from splitspec.schemas import Case, Confidence, VerifierTest
from splitspec.trace import Trace

app = typer.Typer()


def _prepare_frozen_dir(verifier_test: Path, case: Case) -> Path:
    """Turn ``--verifier-test`` into a frozen artifact directory.

    A directory is used as-is; a ``.py`` file (e.g. a gold hidden test) is frozen
    into a throwaway directory first. Everything downstream, including the score,
    runs against a frozen test verified by :func:`load_frozen`.
    """
    p = Path(verifier_test)
    if p.is_dir():
        return p
    if p.is_file() and p.suffix == ".py":
        test = VerifierTest(
            case_id=case.id,
            filename=p.name,
            contents=p.read_text(encoding="utf-8"),
            run_command=f"pytest {p.name}",
            invariant="standalone test scored against the case mutant manifest",
            confidence=Confidence.high,
        )
        tmp = Path(tempfile.mkdtemp(prefix="splitspec-mutate-frozen-"))
        freeze(test, tmp)
        return tmp
    raise ValueError(
        f"--verifier-test must be a frozen artifact dir or a .py test file: {p}"
    )


@app.command()
def main(
    case: Annotated[Path, typer.Option(help="path to cases/issue-07.yaml")],
    verifier_test: Annotated[Path, typer.Option(help="frozen test artifact dir, or a .py test file")],
    output: Annotated[Path, typer.Option(help="path to the output JSON")],
) -> None:
    """Score a frozen verifier test against the case's mutant manifest."""
    load_dotenv()  # CLI edge only; Settings.from_env stays hermetic.
    case_obj = Case.model_validate(yaml.safe_load(Path(case).read_text(encoding="utf-8")))

    frozen_dir = _prepare_frozen_dir(verifier_test, case_obj)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    trace = Trace(output.with_suffix(".trajectory.jsonl"))

    # Throwaway workspace root; each mutant gets its own dir under it.
    ws_tmp = Path(tempfile.mkdtemp(prefix="splitspec-mutate-ws-"))
    try:
        score_mutants(case_obj, frozen_dir, ws_tmp, trace)
    finally:
        shutil.rmtree(ws_tmp, ignore_errors=True)

    # Read the score score_mutants already computed rather than recomputing it here.
    # A second computation drifts: this one counted every mutant, including the ones
    # the manifest flags as unkillable in-process, so the CLI printed 0.8 for the very
    # test whose mutation_results.json said 1.0.
    doc = {
        "case": case_obj.id,
        **json.loads(
            (frozen_dir / MUTATION_RESULTS_FILENAME).read_text(encoding="utf-8")
        ),
    }
    output.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(doc, indent=2, default=str))


if __name__ == "__main__":
    app()
