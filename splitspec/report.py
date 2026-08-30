"""Recompute the result table from committed artifacts (no credentials needed).

    python -m splitspec.report --from artifacts/ --output artifacts/evaluation-results.json

Reproducing this project's headline result should not require three provider keys,
two hours of runtime, and a tolerance for free-tier timeouts — and it should not
require the models to be deterministic, which they are not. A reader who runs the
full sweep gets *their* numbers; a reader who runs this gets *ours*, from the
artifacts committed alongside the claims.

Reads every ``artifacts/<run>/result.json``, skips the failure records a timed-out
pair leaves behind, and prints the same metrics the sweep prints. Nothing here calls
a model or a container.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from splitspec.config import CASES_DIR
from splitspec.metrics import Metric, compute_metrics
from splitspec.reporting import write_evaluation_results
from splitspec.schemas import Case, RunResult

app = typer.Typer()


def load_cases(cases_dir: Path = CASES_DIR) -> dict[str, Case]:
    cases: dict[str, Case] = {}
    for path in sorted(Path(cases_dir).glob("issue-*.yaml")):
        case = Case.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        cases[case.id] = case
    return cases


def load_runs(artifacts_dir: Path) -> tuple[list[RunResult], list[str]]:
    """Return (completed runs, names of pairs that failed before producing a result).

    A pair that raised mid-sweep writes ``{"ok": false, ...}``. That is not a run
    that scored zero — the two are opposite findings — so it is reported separately
    and never enters a denominator.
    """
    runs: list[RunResult] = []
    failed: list[str] = []
    for result_json in sorted(Path(artifacts_dir).glob("*/result.json")):
        name = result_json.parent.name
        try:
            data = json.loads(result_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("ok") is False:
            failed.append(name)
            continue
        try:
            runs.append(RunResult.model_validate(data))
        except Exception:  # noqa: BLE001 - a stray directory is not a run
            continue
    return runs, failed


def _fmt(metric: Metric) -> str:
    if metric.value is None:
        return f"not measured — {metric.reason}"
    value = f"{metric.value:.3f}" if isinstance(metric.value, float) else str(metric.value)
    return f"{value}  (n={metric.denominator})"


@app.command()
def main(
    from_: Annotated[Path, typer.Option("--from", help="artifacts directory")] = Path("artifacts"),
    output: Annotated[
        Path | None, typer.Option(help="write evaluation-results.json here")
    ] = None,
) -> None:
    """Print the result table from artifacts on disk, and optionally write it."""
    cases = load_cases()
    runs, failed = load_runs(from_)
    if not runs:
        raise typer.BadParameter(f"no completed runs found under {from_}")

    baseline = [r for r in runs if r.mode == "baseline"]
    splitspec = [r for r in runs if r.mode == "splitspec"]

    print(f"artifacts   : {from_}")
    print(f"completed   : {len(baseline)} baseline / {len(splitspec)} splitspec")
    if failed:
        print(f"incomplete  : {len(failed)} pair(s) failed before producing a result")
        for name in failed:
            print(f"              {name}")
    print()

    for name, metric in compute_metrics(runs, cases).items():
        print(f"{name:32} {_fmt(metric)}")
        for note in metric.notes:
            print(f"{'':32} - {note}")

    # Reviewer effort is the outcome a maintainer actually feels: how many patches
    # they must read by hand. Reported per mode, with the denominator.
    print()
    for label, group in (("baseline", baseline), ("splitspec", splitspec)):
        correct = [r for r in group if r.gold is not None and r.gold.passed]
        cleared = [r for r in correct if r.decision == "ACCEPT"]
        broken = [r for r in group if r.gold is not None and not r.gold.passed]
        broken_cleared = [r for r in broken if r.decision == "ACCEPT"]
        reviews = [r for r in group if r.decision != "ACCEPT"]
        print(
            f"{label:10} cleared {len(cleared)}/{len(correct)} correct · "
            f"{len(broken_cleared)}/{len(broken)} broken cleared · "
            f"{len(reviews)} human review(s) required"
        )

    if output is not None:
        path = write_evaluation_results(output, runs, cases)
        print(f"\nwrote {path}")


if __name__ == "__main__":
    app()
