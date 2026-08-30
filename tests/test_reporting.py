"""Module 11: review packet + decision rule tests."""
from __future__ import annotations

import json

from splitspec.config import Provider, Settings
from splitspec.reporting import (
    REVIEW_PACKET_FILENAME,
    decide,
    render_packet,
    write_evaluation_results,
    write_packet,
)
from splitspec.schemas import (
    Case,
    Confidence,
    IssueContract,
    Patch,
    RunResult,
    TestRun,
    ValidityGate,
)


def _case(cid: str, *, expect_escalation: bool = False) -> Case:
    return Case(id=cid, title=f"Title {cid}", issue_text="the reported bug",
                fixture="eventpulse", expect_escalation=expect_escalation)


def _tr(label, passed: bool) -> TestRun:
    return TestRun(label=label, command=label, passed=passed)


def _v(passed: bool) -> ValidityGate:
    return ValidityGate(passed=passed, compiles=True, runs=True,
                        fails_on_original_bug=passed)


def _settings() -> Settings:
    def p(role: str) -> Provider:
        return Provider(role=role, base_url=f"http://{role}.x", model=f"model-{role}")
    # fixer and verifier differ on purpose so independence_note says "different".
    return Settings(fixer=p("fixer"), verifier=p("verifier"), contract=p("contract"))


def _accept_run(cid: str = "issue-01") -> RunResult:
    return RunResult(
        case_id=cid, mode="splitspec",
        contract=IssueContract(case_id=cid, summary="s", invariants=["I1"],
                               confidence=Confidence.high),
        visible=_tr("visible", True), gold=_tr("gold", True),
        verifier=_tr("verifier", True), validity=_v(True),
        patch=Patch(case_id=cid, diff="", notes="stop_reason=finished; ok",
                    files_changed=["src.py"], lines_added=2, lines_removed=1),
    )


# ---------------------------------------------------------------------------
# Decision rule: all four outcomes
# ---------------------------------------------------------------------------


def test_decision_accept_when_visible_and_valid_verifier_pass():
    result = _accept_run()
    result.decision = decide(result, _case("issue-01"))
    assert result.decision == "ACCEPT"


def test_decision_escalates_on_low_confidence_contract():
    result = _accept_run()
    result.contract = IssueContract(
        case_id="issue-01", summary="s", invariants=["i"], confidence=Confidence.low
    )
    assert decide(result, _case("issue-01")) == "ESCALATE"


def test_decision_escalates_on_expect_escalation_case():
    result = _accept_run("issue-11")
    assert decide(result, _case("issue-11", expect_escalation=True)) == "ESCALATE"


def test_decision_rejects_when_visible_tests_fail():
    result = _accept_run()
    result.visible = _tr("visible", False)
    assert decide(result, _case("issue-01")) == "REJECT"


def test_decision_rejects_when_patch_edited_an_existing_test():
    result = _accept_run()
    result.patch.touched_tests = True
    assert decide(result, _case("issue-01")) == "REJECT"


def test_decision_does_not_reject_for_adding_a_test():
    """A patch that only ADDS a test (touched_tests=False) must not be REJECTed."""
    result = _accept_run()
    result.patch.touched_tests = False
    result.patch.files_changed = ["test_added.py"]
    assert decide(result, _case("issue-01")) == "ACCEPT"


def test_decision_review_required_without_verifier():
    """No verifier branch (baseline-ish) => cannot ACCEPT, not a REJECT either."""
    result = _accept_run()
    result.verifier = None
    result.validity = None
    assert decide(result, _case("issue-01")) == "REVIEW REQUIRED"


def test_decision_review_required_when_verifier_is_invalid_gated():
    result = _accept_run()
    result.validity = _v(False)  # test never earned the right to judge
    assert decide(result, _case("issue-01")) == "REVIEW REQUIRED"


# ---------------------------------------------------------------------------
# Stop reason extraction from Patch.notes
# ---------------------------------------------------------------------------


def test_stop_reason_from_patch_notes():
    from splitspec.reporting import _stop_reason

    assert _stop_reason(Patch(case_id="x", diff="", notes="stop_reason=finished; ok")) == "finished"
    assert _stop_reason(Patch(case_id="x", diff="", notes="stop_reason=max_tokens")) == "max_tokens"
    assert _stop_reason(None) == "n/a (no patch)"
    # A truncated attempt is surfaced, not hidden.
    assert _stop_reason(Patch(case_id="x", diff="", notes="stop_reason=budget_exceeded")) == \
        "budget_exceeded"


# ---------------------------------------------------------------------------
# Rendering: every PROJECT.md §14 section is present
# ---------------------------------------------------------------------------


def test_render_packet_has_every_project14_section():
    result = _accept_run()
    result.verifier_test = None
    text = render_packet(result, _case("issue-01"), _settings())
    for section in (
        "# SplitSpec Review Packet — Issue issue-01",
        "## Decision",
        "## Issue",
        "## Behavioral invariant",
        "## Candidate patch",
        "## Visible tests",
        "## Independent verifier test",
        "## Gold hidden evaluator",
        "## Mutation sensitivity",
        "## Residual risks",
        "## Human action",
    ):
        assert section in text, f"missing section: {section}"


def test_packet_surfaces_stop_reason_independence_and_human_review():
    result = _accept_run("issue-07")
    result.patch.notes = "stop_reason=budget_exceeded; half done"
    text = render_packet(result, _case("issue-07"), _settings())
    assert "stop_reason=budget_exceeded" in text \
        or "budget_exceeded" in text, "stop reason must be surfaced"
    # Residual risks flags the truncated patch explicitly.
    assert "truncated attempt" in text
    # Independence note is always recorded.
    assert "independence" in text.lower()
    # Human must review; SplitSpec merged nothing.
    assert "human must review" in text
    assert "SplitSpec merged nothing" in text


def test_decision_is_rendered_in_packet():
    result = _accept_run()
    result.decision = decide(result, _case("issue-01"))
    text = render_packet(result, _case("issue-01"), _settings())
    assert "## Decision\nACCEPT" in text


# ---------------------------------------------------------------------------
# write_packet / write_evaluation_results write real files
# ---------------------------------------------------------------------------


def test_write_packet_round_trips_to_artifact_dir(tmp_path):
    result = _accept_run("issue-07")
    result.decision = decide(result, _case("issue-07"))
    path = write_packet(tmp_path, result, _case("issue-07"), _settings())
    assert path.name == REVIEW_PACKET_FILENAME
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# SplitSpec Review Packet — Issue issue-07")


def test_write_evaluation_results_writes_metrics_and_rows(tmp_path):
    cases = {c.id: c for c in [_case("issue-01"), _case("issue-07")]}
    runs = [
        _accept_run("issue-01"),
        _accept_run("issue-07"),
    ]
    for r in runs:
        r.decision = decide(r, cases[r.case_id])
    out = tmp_path / "evaluation-results.json"
    write_evaluation_results(out, runs, cases)
    data = json.loads(out.read_text())
    assert "metrics" in data and "rows" in data
    assert any(
        row["case_id"] == "issue-01" and row["decision"] == "ACCEPT"
        for row in data["rows"]
    )
    # cost is unmeasured -> metrics reports None with a reason, never a fabricated 0
    cost = data["metrics"]["median_model_cost_usd"]
    assert cost["value"] is None
    assert "unmeasured" in cost["reason"]


def test_packet_decision_is_computed_not_the_stored_field():
    """The rendered headline must agree with the inputs printed beneath it.

    RunResult.decision can hold a stale default (every run written before the
    decision rule existed carries "REVIEW REQUIRED"). Rendering that verbatim puts
    a REVIEW REQUIRED banner directly above "Visible tests: FAIL", which is the one
    thing a reviewer must be able to trust at a glance.
    """
    case = _case("issue-07")
    result = _accept_run("issue-07")
    result.visible = _tr("visible", False)
    result.decision = "REVIEW REQUIRED"  # stale stored value
    assert decide(result, case) == "REJECT"
    packet = render_packet(result, case, _settings())
    assert "REJECT" in packet
    assert "REVIEW REQUIRED" not in packet.split("## Issue")[0]
