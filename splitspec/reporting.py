"""Review packets and decision rule (Module 11).

Renders the PROJECT.md §14 review packet from a :class:`RunResult` + :class:`Case`
(+ :class:`Settings` for the independence note), computes the defensive decision
rule, and emits the HLD §7 result table used by ``evaluation-results.json``.

The decision rule the grader expects (LLD Module 11 popout, confirmed by the user):

- ``ESCALATE`` when the contract is low-confidence OR ``case.expect_escalation``.
- ``REJECT`` when visible tests fail, OR the patch edited an *existing* test
  (``Patch.touched_tests``). Adding a test is not a rejection.
- ``ACCEPT`` only when visible AND a *valid* verifier test both pass (validity
  gate passed and the verifier suite passed).
- otherwise ``REVIEW REQUIRED``.

The rule is printed together with its inputs so a human can see why a decision was
reached instead of trusting a bare label.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from splitspec.config import ROOT, Settings
from splitspec.metrics import compute_metrics
from splitspec.schemas import Case, Confidence, Patch, RunResult, TestRun

TEMPLATES_DIR = ROOT / "splitspec" / "templates"
REVIEW_PACKET_FILENAME = "review_packet.md"
_STOP_FINISHED = "finished"


def decide(result: RunResult, case: Case) -> str:
    """The defensive decision rule; returns one of the four decision strings."""
    low_confidence = (
        result.contract is not None
        and result.contract.confidence == Confidence.low
    )
    if low_confidence or case.expect_escalation:
        return "ESCALATE"

    visible_failed = result.visible is not None and not result.visible.passed
    touched = result.patch is not None and result.patch.touched_tests
    if visible_failed or touched:
        return "REJECT"

    valid_verifier = (
        result.validity is not None and result.validity.passed
        and result.verifier is not None and result.verifier.passed
    )
    if result.visible is not None and result.visible.passed and valid_verifier:
        return "ACCEPT"

    return "REVIEW REQUIRED"


def _stop_reason(patch: Patch | None) -> str:
    """The fixer records its stop reason in ``Patch.notes`` as ``stop_reason=...``."""
    if patch is None or not patch.notes:
        return "n/a (no patch)"
    if patch.notes.startswith("stop_reason="):
        rest = patch.notes[len("stop_reason="):]
        end = rest.find(";")
        return rest[:end].strip() if end != -1 else rest.strip()
    return patch.notes.strip()


def _suite_line(run: TestRun | None) -> str:
    if run is None:
        return "n/a"
    verdict = "PASS" if run.passed else "FAIL"
    return f"{verdict} - {run.total} tests, {run.failures} failed, {run.errors} errors"


def _validity_note(result: RunResult) -> str:
    if result.validity is None:
        return "no validity gate recorded (test never earned the right to grade)"
    parts = [
        f"compiles={result.validity.compiles}",
        f"runs={result.validity.runs}",
        f"fails_on_original_bug={result.validity.fails_on_original_bug}",
    ]
    verdict = "valid" if result.validity.passed else "invalid/gated"
    text = f"{verdict} ({', '.join(parts)})"
    if result.validity.reason:
        text += f" — {result.validity.reason}"
    return text


def _mutation_note(result: RunResult) -> str:
    if not result.mutation:
        return "no mutants scored (baseline run, or none applicable)"
    killed = sum(1 for m in result.mutation if m.killed)
    total = len(result.mutation)
    note = f"Detected {killed}/{total} incorrect variants"
    if 0 < killed < total:
        note += (
            ". A below-ceiling score may reflect a mutant no in-process test can "
            "kill (a manifest ceiling), not a test failure."
        )
    return note


def _residual_risks(result: RunResult, case: Case) -> list[str]:
    risks: list[str] = []
    if result.degraded:
        risks.append(
            f"Run was degraded ({result.degraded_reason or 'a role fell back'}); "
            "it is excluded from the headline metric."
        )
    stop = _stop_reason(result.patch) if result.patch is not None else "n/a"
    if stop != _STOP_FINISHED:
        risks.append(
            f"Fixer stopped with reason '{stop}' rather than 'finished' — the patch "
            "may be a truncated attempt and evidence below may be partial."
        )
    for a in (result.contract.ambiguities if result.contract else []):
        risks.append(f"Contract ambiguity: {a}")
    for s in (result.contract.out_of_scope if result.contract else []):
        risks.append(f"Out of scope (unaddressed): {s}")
    if case.expect_escalation:
        risks.append(
            "Case is marked expect_escalation; it is scored on whether the run "
            "escalated, not on patch correctness."
        )
    return risks


def build_packet_context(result: RunResult, case: Case, settings: Settings) -> dict:
    """Assemble the template context from a run + case + settings."""
    contract = result.contract
    patch = result.patch

    def verdict(run: TestRun | None) -> str:
        if run is None:
            return "n/a"
        return "PASS" if run.passed else "FAIL"

    return {
        "case": case,
        "packet": {
            # Compute the decision from the run rather than trusting the stored
            # field. A stored value can be a stale default, and the packet then
            # prints a headline that contradicts the decision inputs listed
            # directly beneath it - a REVIEW REQUIRED banner above "Visible
            # tests: FAIL" is exactly the packet a human should not have to
            # second-guess.
            "decision": decide(result, case),
            "confidence": contract.confidence.value if contract else "n/a (no contract)",
            "expect_escalation": str(case.expect_escalation),
            "visible_verdict": verdict(result.visible),
            "visible_ran": str(result.visible is not None),
            "verifier_verdict": verdict(result.verifier),
            "verifier_valid": str(
                result.validity is not None and result.validity.passed
            ),
            "verifier_ran": str(result.verifier is not None),
            "touched_tests": str(bool(patch and patch.touched_tests)),
            "issue_text": case.issue_text,
            "out_of_scope": ", ".join(contract.out_of_scope) if contract else "",
            "invariants": contract.invariants if contract else [],
            "files_changed": (
                ", ".join(patch.files_changed) if patch and patch.files_changed else "n/a"
            ),
            "lines_added": patch.lines_added if patch else 0,
            "lines_removed": patch.lines_removed if patch else 0,
            "stop_reason": _stop_reason(patch),
            "patch_notes": (patch.notes or "n/a") if patch else "n/a",
            "visible_line": _suite_line(result.visible),
            "visible_tail": (result.visible.stdout_tail or "").strip() if result.visible else "",
            "verifier_line": _suite_line(result.verifier),
            "verifier_invariant": (
                result.verifier_test.invariant if result.verifier_test else ""
            ),
            "verifier_assumptions": (
                result.verifier_test.assumptions if result.verifier_test else []
            ),
            "validity_note": _validity_note(result),
            "gold_line": _suite_line(result.gold),
            "mutation_note": _mutation_note(result),
            "mutation_items": bool(result.mutation),
            "mutation_killed": sum(1 for m in result.mutation if m.killed),
            "mutation_denominator": len(result.mutation),
            "residual_risks": _residual_risks(result, case),
            "independence_note": settings.independence_note(),
            "human_action": (
                "Review the evidence in this packet and either approve or reject the "
                "patch. Judge the patch against the gold hidden evaluator's result, "
                "the verifier's independence note, and the mutation sensitivity before "
                "deciding."
            ),
        },
    }


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_packet(result: RunResult, case: Case, settings: Settings) -> str:
    """Render the §14 review packet for a single run."""
    context = build_packet_context(result, case, settings)
    template = _env().get_template("review_packet.md.j2")
    return template.render(**context)


def write_packet(
    artifact_dir: Path, result: RunResult, case: Case, settings: Settings
) -> Path:
    """Write ``review_packet.md`` into the run's artifact directory."""
    text = render_packet(result, case, settings)
    path = Path(artifact_dir) / REVIEW_PACKET_FILENAME
    path.write_text(text, encoding="utf-8")
    return path


def evaluation_results(runs: list[RunResult], cases: dict[str, Case]) -> dict:
    """The HLD §7 result table + per-issue/per-mode medians, for evaluation-results.

    ``metrics`` holds the aggregate values (None where unmeasured, with reason);
    ``rows`` is one dict per run for the sweep summary.
    """
    metrics = compute_metrics(runs, cases)
    rows = [
        {
            "case_id": r.case_id,
            "mode": r.mode,
            "decision": r.decision,
            "degraded": r.degraded,
            "runtime_sec": r.runtime_sec,
            "cost_usd": r.cost_usd,
            "visible": r.visible.passed if r.visible else None,
            "verifier": r.verifier.passed if r.verifier else None,
            "gold": r.gold.passed if r.gold else None,
            "mutation_killed": sum(1 for m in r.mutation if m.killed),
            "mutation_denominator": len(r.mutation),
        }
        for r in runs
    ]
    return {
        "metrics": {
            name: {
                "value": m.value,
                "denominator": m.denominator,
                "reason": m.reason,
                "notes": m.notes,
            }
            for name, m in metrics.items()
        },
        "rows": rows,
    }


def write_evaluation_results(
    path: Path, runs: list[RunResult], cases: dict[str, Case]
) -> Path:
    import json

    path = Path(path)
    path.write_text(
        json.dumps(evaluation_results(runs, cases), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
