"""Resumable multi-case evaluation sweep CLI (Module 9).

`python -m splitspec.evaluate --cases cases/ --modes baseline,splitspec
--output artifacts/evaluation-results.json`

Iterates every case/mode pair and writes each run's artifact set under
``<output-dir>/<case>-<mode>/`` and accumulates ``evaluation-results.json``.

Resumability is a first-class feature, not an afterthought: it is the answer to a
provider's daily free-tier quota. A pair whose ``result.json`` is already complete
is **skipped** unless ``--force``, so an interrupted sweep resumes where it left
off. A pair that raises mid-run is recorded in its own ``result.json`` and the
sweep moves on -- losing eleven good cases to one provider error is the worst
possible outcome, so one failure must never abort the batch.

Cases run sequentially by default (deterministic ordering); ``--parallel N > 1``
runs them concurrently.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from splitspec.config import Settings, load_dotenv
from splitspec.run import run_case
from splitspec.schemas import Case, Mode, RunResult

app = typer.Typer()


def _load_case(path: Path) -> Case:
    return Case.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _complete(result_json: Path) -> bool:
    """True when a pair's result.json holds a complete, successful RunResult.

    A failure record written by :func:`_write_error` carries only ``case_id`` and
    ``mode`` beyond its ``ok``/``error`` keys, and every other RunResult field has
    a default - so it VALIDATES as a RunResult. Treating that as complete would
    make resume skip exactly the pairs that failed, which is the opposite of what
    resume exists for: the usual reason a pair fails is a provider quota, and the
    whole point of re-running tomorrow is to retry those. So the failure marker is
    checked before validation, not after.
    """
    if not result_json.is_file():
        return False
    try:
        data = json.loads(result_json.read_text(encoding="utf-8"))
    except Exception:
        return False
    if isinstance(data, dict) and data.get("ok") is False:
        return False
    try:
        RunResult.model_validate(data)
        return True
    except Exception:
        return False


def _write_error(result_json: Path, case: Case, mode: Mode, error: str) -> dict[str, Any]:
    """Write a result.json that records a failure, then return that record.

    The sweep must be able to say "this pair failed" without aborting the rest, so
    a failure is a first-class, inspectable record, not a bare exception.
    """
    record = {"case_id": case.id, "mode": mode, "ok": False, "error": str(error)}
    result_json.parent.mkdir(parents=True, exist_ok=True)
    result_json.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def _run_pair(
    case: Case,
    mode: Mode,
    artifact_dir: Path,
    settings: Settings,
    force: bool,
) -> dict[str, Any]:
    result_json = artifact_dir / "result.json"
    if not force and _complete(result_json):
        return json.loads(result_json.read_text(encoding="utf-8"))
    try:
        result = run_case(case, mode, artifact_dir, settings=settings)
        result_json.write_text(
            result.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        return result.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - one failure must not abort the sweep
        return _write_error(result_json, case, mode, exc)


@app.command()
def evaluate(
    cases: Annotated[Path, typer.Option(help="directory containing issue-*.yaml")],
    modes: Annotated[str, typer.Option(help="comma-separated modes, e.g. baseline,splitspec")],
    output: Annotated[Path, typer.Option(help="path to the evaluation-results.json")],
    parallel: Annotated[int, typer.Option(help="concurrent cases (1 = deterministic, sequential)")] = 1,
    force: Annotated[bool, typer.Option(help="re-run even a pair with a complete result.json")] = False,
) -> None:
    """Run every case/mode pair, resumably, and write evaluation-results.json."""
    load_dotenv()
    settings = Settings.from_env()
    mode_list = [m for m in (s.strip() for s in modes.split(",")) if m]
    case_files = sorted(Path(cases).glob("issue-*.yaml"))
    artifact_parent = Path(output).parent
    artifact_parent.mkdir(parents=True, exist_ok=True)

    pairs: list[tuple[Case, Mode, Path]] = []
    for case_file in case_files:
        case = _load_case(case_file)
        for mode in mode_list:
            pairs.append((case, mode, artifact_parent / f"{case.id}-{mode}"))

    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            collected = list(
                pool.map(lambda p: _run_pair(*p, settings, force), pairs)
            )
    else:
        collected = [_run_pair(c, m, d, settings, force) for c, m, d in pairs]

    summary = {
        "output": str(Path(output).resolve()),
        "total": len(collected),
        "ok": sum(1 for r in collected if r.get("ok", True)),
        "results": {f"{r['case_id']}-{r['mode']}": r for r in collected},
    }
    Path(output).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
