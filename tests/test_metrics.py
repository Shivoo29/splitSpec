"""Module 11: metrics tests.

Every expected value is computed by hand from the fixture, not copied from the
implementation, so a wrong formula cannot smuggle itself in as a passing test.
"""
from __future__ import annotations

from splitspec.metrics import (
    compute_metrics,
    correct_patch_acceptance_rate,
    false_fix_detection_recall,
    false_rejection_rate,
    generated_test_validity_rate,
    median_model_cost,
    median_runtime,
    mutation_score,
)
from splitspec.schemas import Case, MutationResult, RunResult, TestRun, ValidityGate


def _case(cid: str, expect_escalation: bool = False) -> Case:
    return Case(id=cid, title=cid, issue_text="x", fixture="eventpulse",
                expect_escalation=expect_escalation)


def _tr(label, passed: bool) -> TestRun:
    return TestRun(label=label, command=label, passed=passed)


def _v(passed: bool) -> ValidityGate:
    return ValidityGate(passed=passed, compiles=True, runs=True,
                        fails_on_original_bug=passed)


def _run(cid: str, *, mode="splitspec", visible=None, gold=None, verifier=None,
         validity=None, runtime=0.0, cost=0.0, mutation=None, degraded=False) -> RunResult:
    return RunResult(
        case_id=cid, mode=mode, visible=visible, gold=gold, verifier=verifier,
        validity=validity, runtime_sec=runtime, cost_usd=cost,
        mutation=mutation or [], degraded=degraded,
    )


def _cases(*cases: Case) -> dict[str, Case]:
    return {c.id: c for c in cases}


# ---------------------------------------------------------------------------
# False fix detection recall (the primary metric)
# ---------------------------------------------------------------------------


def test_recall_counts_only_caught_shallow_fixes():
    cases = _cases(_case("issue-02"))
    runs = [
        # visible pass + gold fail = a shallow fix the visible suite missed.
        _run("issue-02", visible=_tr("visible", True), gold=_tr("gold", False),
             verifier=_tr("verifier", True)),   # verifier MISSED it -> not caught
        _run("issue-02", visible=_tr("visible", True), gold=_tr("gold", False),
             verifier=_tr("verifier", False)),  # caught
        _run("issue-02", visible=_tr("visible", True), gold=_tr("gold", False),
             verifier=_tr("verifier", False)),  # caught
        # Not part of the denominator: gold actually passed.
        _run("issue-02", visible=_tr("visible", True), gold=_tr("gold", True),
             verifier=_tr("verifier", True)),
    ]
    m = false_fix_detection_recall(runs, cases)
    assert m.denominator == 3
    assert m.value == 2 / 3


def test_recall_is_none_with_reason_when_all_degraded():
    cases = _cases(_case("issue-02"))
    runs = [
        _run("issue-02", visible=_tr("visible", True), gold=_tr("gold", False),
             verifier=_tr("verifier", True), degraded=True),
        _run("issue-02", visible=_tr("visible", True), gold=_tr("gold", False),
             verifier=_tr("verifier", True), degraded=True),
    ]
    m = false_fix_detection_recall(runs, cases)
    assert m.value is None
    assert "no non-degraded" in m.reason


def test_recall_excludes_runs_without_a_verifier_verdict():
    cases = _cases(_case("issue-02"))
    # baseline run (no verifier at all) and a run with an invalid-gated verifier
    # that never produced a verdict -> neither can be judged caught-or-missed.
    runs = [
        _run("issue-02", mode="baseline", visible=_tr("visible", True),
             gold=_tr("gold", False)),
        _run("issue-02", visible=_tr("visible", True), gold=_tr("gold", False),
             verifier=None, validity=_v(False)),
    ]
    m = false_fix_detection_recall(runs, cases)
    assert m.value is None
    assert m.denominator == 0


# ---------------------------------------------------------------------------
# Acceptance and rejection rates
# ---------------------------------------------------------------------------


def test_acceptance_and_rejection_denominators_hand_computed():
    cases = _cases(_case("issue-04"))
    correct = _tr("gold", True)
    runs = [
        # A: correct, accepted (visible + verifier pass).
        _run("issue-04", visible=_tr("visible", True), gold=correct,
             verifier=_tr("verifier", True), validity=_v(True)),
        # B: correct, verifier fails -> false rejection.
        _run("issue-04", visible=_tr("visible", True), gold=correct,
             verifier=_tr("verifier", False), validity=_v(True)),
        # C: correct, visible fails -> false rejection.
        _run("issue-04", visible=_tr("visible", False), gold=correct,
             verifier=_tr("verifier", True), validity=_v(True)),
        # D: invalid-gated verifier -> excluded from acceptance & rejection.
        _run("issue-04", visible=_tr("visible", True), gold=correct,
             verifier=_tr("verifier", True), validity=_v(False)),
    ]
    acc = correct_patch_acceptance_rate(runs, cases)
    rj = false_rejection_rate(runs, cases)
    assert (acc.denominator, rj.denominator) == (3, 3)
    assert acc.value == 1 / 3
    assert rj.value == 2 / 3


def test_acceptance_excludes_expect_escalation_cases():
    cases = _cases(_case("issue-11", expect_escalation=True))
    correct = _tr("gold", True)
    runs = [
        # Correct patch, everything passes, but the case must be scored on
        # escalation, never on patch correctness.
        _run("issue-11", visible=_tr("visible", True), gold=correct,
             verifier=_tr("verifier", True), validity=_v(True)),
    ]
    acc = correct_patch_acceptance_rate(runs, cases)
    rj = false_rejection_rate(runs, cases)
    assert acc.value is None and acc.denominator == 0
    assert rj.value is None and rj.denominator == 0


# ---------------------------------------------------------------------------
# Generated test validity rate
# ---------------------------------------------------------------------------


def test_validity_rate_counts_invalid_gated_tests_in_the_denominator():
    cases = _cases(_case("issue-06"))
    runs = [
        _run("issue-06", validity=_v(True)),
        _run("issue-06", validity=_v(True)),
        _run("issue-06", validity=_v(False)),
    ]
    m = generated_test_validity_rate(runs, cases)
    assert m.denominator == 3, "invalid-gated tests still count in the denominator"
    assert m.value == 2 / 3


# ---------------------------------------------------------------------------
# Mutation score
# ---------------------------------------------------------------------------


def test_mutation_score_pools_killed_over_denominator():
    cases = _cases(_case("issue-07"))
    runs = [
        _run("issue-07", mutation=[
            MutationResult(mutant_id="m1", description="d", killed=True),
            MutationResult(mutant_id="m2", description="d", killed=True),
        ]),
        _run("issue-07", mutation=[
            MutationResult(mutant_id="m1", description="d", killed=True),
            MutationResult(mutant_id="m2", description="d", killed=False),
            MutationResult(mutant_id="m3", description="d", killed=False),
        ]),
    ]
    m = mutation_score(runs, cases)
    assert m.denominator == 5
    assert m.value == 3 / 5
    # Every mutant here is scorable, so there is nothing to note.
    assert m.notes == []


def test_mutation_score_excludes_unkillable_mutants_and_says_so():
    """A mutant no test in this harness can kill must stay out of the denominator.

    issue-07's m07-2 adds a threading.Lock, which genuinely serializes the race
    inside the single process every oracle here runs in. Counting it caps every
    achievable score below 1.0 and makes a perfect test look like it missed one -
    and it would put a different score here than the one mutation_results.json
    already wrote for the same run.
    """
    cases = _cases(_case("issue-07"))
    runs = [
        _run("issue-07", mutation=[
            MutationResult(mutant_id="m07-1", description="d", killed=True),
            MutationResult(mutant_id="m07-2", description="d", killed=False, scored=False),
            MutationResult(mutant_id="m07-3", description="d", killed=True),
        ]),
    ]
    m = mutation_score(runs, cases)
    assert m.denominator == 2, "the unkillable mutant inflated the denominator"
    assert m.value == 1.0
    assert any("m07-2" in n and "unkillable" in n for n in m.notes)


# ---------------------------------------------------------------------------
# Runtime and (unmeasured) model cost medians
# ---------------------------------------------------------------------------


def test_median_runtime_excludes_degraded_and_returns_hand_median():
    cases = _cases(_case("issue-04"))
    runs = [
        _run("issue-04", runtime=1.0),
        _run("issue-04", runtime=3.0),
        _run("issue-04", runtime=2.0),
        _run("issue-04", runtime=100.0, degraded=True),  # excluded
    ]
    m = median_runtime(runs, cases)
    assert m.denominator == 3
    assert m.value == 2.0


def test_median_cost_is_none_with_reason_when_unmeasured():
    cases = _cases(_case("issue-04"))
    # Real runs have cost 0.0 because the agents drop model_use. Reporting a
    # median of zeros would fabricate a finding; None + reason is the honest answer.
    runs = [_run("issue-04", cost=0.0), _run("issue-04", cost=0.0)]
    m = median_model_cost(runs, cases)
    assert m.value is None
    assert "unmeasured" in m.reason
    assert m.denominator == 0


def test_median_cost_computes_when_cost_is_measured():
    cases = _cases(_case("issue-04"))
    runs = [_run("issue-04", cost=1.0), _run("issue-04", cost=2.0),
            _run("issue-04", cost=3.0)]
    m = median_model_cost(runs, cases)
    assert m.value == 2.0
    assert m.denominator == 3


def test_compute_metrics_returns_the_full_rld7_table():
    cases = _cases(_case("issue-04"), _case("issue-07"))
    runs = [
        _run("issue-04", visible=_tr("visible", True), gold=_tr("gold", True),
             verifier=_tr("verifier", True), validity=_v(True), runtime=2.0),
        _run("issue-07", visible=_tr("visible", True), gold=_tr("gold", False),
             verifier=_tr("verifier", False), validity=_v(True), runtime=4.0,
             mutation=[MutationResult(mutant_id="m1", description="d", killed=True)]),
    ]
    table = compute_metrics(runs, cases)
    assert set(table) == {
        "false_fix_detection_recall",
        "correct_patch_acceptance_rate",
        "false_rejection_rate",
        "generated_test_validity_rate",
        "mutation_score",
        "median_runtime_sec",
        "median_model_cost_usd",
    }
    assert table["false_fix_detection_recall"].value == 1.0
    assert table["correct_patch_acceptance_rate"].value == 1.0
    assert table["mutation_score"].value == 1.0
    assert table["median_runtime_sec"].value == 3.0
