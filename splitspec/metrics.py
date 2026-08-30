"""Aggregate metrics (Module 11).

Implements exactly the formulas in docs/HLD.md section 7, over a list of
:class:`~splitspec.schemas.RunResult` plus a case map (case_id -> Case) so the
rules that need the case can see them (e.g. ``expect_escalation``).

Ground rules that are stricter than the formulas:

- **Missing data is None with a stated reason, never 0.** A zero recall and an
  unmeasured recall are opposite findings and must not be conflated. Every metric
  returns a :class:`Metric` carrying ``value`` (None when unmeasured), the
  ``denominator`` it was computed over (so a rate over 2 cases is visibly not a
  finding), and a ``reason``.
- **The denominator is reported with every rate.** 50% over two cases is not 50%
  over twelve.
- **A degraded run is excluded** from every inferential metric below, and the
  exclusion is surfaced through the returned Metrics rather than being silent.
- **An invalid-gated verifier** (``validity.passed`` is False) is excluded from
  the acceptance and rejection rates but still counts in the validity-rate
  denominator: a test that passed on the buggy code never earned the right to
  judge, yet it was still *generated* and thus belongs in the validity numerator
  or denominator.
- **Case 11 (``expect_escalation``) is scored on whether it escalated**, never on
  patch correctness. Counting an ambiguous, no-fix issue as a failed fix would be
  wrong, so those runs are excluded from acceptance/rejection.
- **Cost is currently unmeasured.** :func:`run_agent` accumulates real token
  counts, but :func:`run_fixer`/:func:`run_verifier` return only Patch/VerifierTest
  and drop ``model_use``, so every real ``RunResult.cost_usd`` is 0.0. We therefore
  report modelled cost as None with that reason rather than fabricated zeros.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from splitspec.schemas import Case, RunResult


@dataclass
class Metric:
    """One aggregate: value (None = unmeasured), denominator, and why."""

    value: float | int | None
    denominator: int = 0
    reason: str = ""
    notes: list[str] = field(default_factory=list)


Cases = dict[str, Case]


def _median(values: list[float | int]) -> float:
    return float(statistics.median(values))


def false_fix_detection_recall(runs: list[RunResult], cases: Cases) -> Metric:
    """Primary. Of patches that passed visible yet failed gold (a shallow fix the
    visible suite could not see), the fraction the independent verifier caught.

    Denominator: non-degraded splitspec runs with visible=pass, gold=fail, and a
    verifier verdict. A run whose verifier test was gated invalid has no verdict
    and cannot be counted as caught or missed, so it is excluded here.
    """
    pool = [
        r for r in runs
        if (not r.degraded and r.mode == "splitspec"
            and r.visible is not None and r.visible.passed
            and r.gold is not None and not r.gold.passed
            and r.verifier is not None)
    ]
    if not pool:
        return Metric(
            None, 0,
            "no non-degraded splitspec run with visible-pass & gold-fail and a verifier verdict",
        )
    caught = [r for r in pool if not r.verifier.passed]
    return Metric(len(caught) / len(pool), len(pool))


def _correct_non_escalation_valid(runs: list[RunResult], cases: Cases) -> list[RunResult]:
    """Correct (gold passed), non-escalation, valid-verifier, non-degraded runs —
    the denominator pool for acceptance and rejection rates."""
    return [
        r for r in runs
        if (not r.degraded and r.gold is not None and r.gold.passed
            and not cases[r.case_id].expect_escalation
            and r.validity is not None and r.validity.passed
            and r.verifier is not None)
    ]


def correct_patch_acceptance_rate(runs: list[RunResult], cases: Cases) -> Metric:
    """Of correct patches (gold passed) with a valid verifier, the fraction the
    system accepted (visible and verifier both passed)."""
    pool = _correct_non_escalation_valid(runs, cases)
    if not pool:
        return Metric(None, 0, "no correct, non-escalation, valid-verifier runs")
    accepted = [
        r for r in pool
        if r.visible is not None and r.visible.passed and r.verifier is not None
        and r.verifier.passed
    ]
    return Metric(len(accepted) / len(pool), len(pool))


def false_rejection_rate(runs: list[RunResult], cases: Cases) -> Metric:
    """Of correct patches with a valid verifier, the fraction wrongly rejected
    (visible failed, or the verifier failed a correct patch)."""
    pool = _correct_non_escalation_valid(runs, cases)
    if not pool:
        return Metric(None, 0, "no correct, non-escalation, valid-verifier runs")
    rejected = [
        r for r in pool
        if (r.visible is not None and not r.visible.passed) or not r.verifier.passed
    ]
    return Metric(len(rejected) / len(pool), len(pool))


def generated_test_validity_rate(runs: list[RunResult], cases: Cases) -> Metric:
    """Of generated verifier tests actually assessed by the gate, the fraction
    that were valid (compile ∧ run ∧ fail on the original bug).

    Every assessed test counts in the denominator — including ones the gate marked
    invalid. That is exactly what the prompt insists on.
    """
    pool = [
        r for r in runs
        if not r.degraded and r.mode == "splitspec" and r.validity is not None
    ]
    if not pool:
        return Metric(None, 0, "no non-degraded splitspec run with a validity gate")
    valid = [r for r in pool if r.validity.passed]
    return Metric(len(valid) / len(pool), len(pool))


def mutation_score(runs: list[RunResult], cases: Cases) -> Metric:
    """Pooled killed / denominator across every run that scored mutants.

    A per-case score may sit below 1.0 because a manifest contains a mutant no
    in-process test can kill (issue-07's m07-2 is one): that is a manifest ceiling,
    not a test failure, and the caller must not describe it as one.
    """
    pool = [r for r in runs if not r.degraded and r.mutation]
    # Only mutants marked `scored` count. A mutant the manifest flags as unkillable
    # in this harness is reported but never in a denominator - counting it here
    # while mutation_results.json excludes it would put two different scores for
    # the same run in the same artifact set.
    killed = sum(sum(1 for m in r.mutation if m.scored and m.killed) for r in pool)
    denominator = sum(sum(1 for m in r.mutation if m.scored) for r in pool)
    if not pool or denominator == 0:
        return Metric(None, 0, "no mutation results to score")
    metric = Metric(killed / denominator, denominator)
    # A below-ceiling case is a property of the manifest, not a test failure.
    for r in pool:
        unscored = [m.mutant_id for m in r.mutation if not m.scored]
        if unscored:
            metric.notes.append(
                f"{r.case_id}: {', '.join(unscored)} excluded as unkillable in this "
                "harness; the score is over the remaining mutants"
            )
    return metric


def median_runtime(runs: list[RunResult], cases: Cases) -> Metric:
    values = sorted(r.runtime_sec for r in runs if not r.degraded)
    if not values:
        return Metric(None, 0, "no non-degraded runs with a runtime")
    return Metric(_median(values), len(values))


def median_model_cost(runs: list[RunResult], cases: Cases) -> Metric:
    """Median model cost. Cost is currently unmeasured everywhere (real
    ``cost_usd`` is 0.0 because the agents drop ``model_use``), so this is None
    with that reason, never 0. It still computes when a measured cost exists."""
    values = sorted(r.cost_usd for r in runs if not r.degraded and r.cost_usd > 0)
    if not values:
        return Metric(
            None, 0,
            "model cost is unmeasured: run_agent tracks tokens but run_fixer/"
            "run_verifier drop model_use, so RunResult.cost_usd is 0.0",
        )
    return Metric(_median(values), len(values))


def compute_metrics(runs: list[RunResult], cases: Cases) -> dict[str, Metric]:
    """The HLD §7 result table, keyed by metric name."""
    return {
        "false_fix_detection_recall": false_fix_detection_recall(runs, cases),
        "correct_patch_acceptance_rate": correct_patch_acceptance_rate(runs, cases),
        "false_rejection_rate": false_rejection_rate(runs, cases),
        "generated_test_validity_rate": generated_test_validity_rate(runs, cases),
        "mutation_score": mutation_score(runs, cases),
        "median_runtime_sec": median_runtime(runs, cases),
        "median_model_cost_usd": median_model_cost(runs, cases),
    }
