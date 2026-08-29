"""Verifier agent (Module 7).

Wraps the shared Module 5 tool loop into a verifier-specific :class:`VerifierTest`
producer. It receives the **same** :class:`IssueContract` the fixer got, on its own
workspace at the buggy pre-patch state, and returns the behavioral test the judge
will later grade with.

The information boundary is enforced at entry, inverted from the fixer: the
verifier workspace must contain no fixer patch/artifact and no gold test. A leak
here gives the verifier the answer it is supposed to generate, so it is a hard
assertion that raises immediately, not a log line.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from splitspec.config import GOLD_TESTS_DIR, Settings
from splitspec.llm import ModelClient
from splitspec.sandbox import Workspace
from splitspec.schemas import Case, IssueContract, VerifierTest
from splitspec.tools import default_tools, run_agent
from splitspec.trace import Trace

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "verifier.md"

#: The patch artifact the fixer writes (PROJECT.md §13); never reachable here.
_FIXER_ARTIFACT = "fixer_patch.diff"


class VerifierError(RuntimeError):
    """The verifier's final message could not be turned into a valid VerifierTest."""


def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _assert_no_fixer_or_gold(workspace: Workspace) -> None:
    """Hard boundary: no fixer artifact and no gold test inside the workspace."""
    gold_dir = GOLD_TESTS_DIR.name
    for path in sorted(Path(workspace.path).rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(workspace.path)
        parts = set(rel.parts)
        if gold_dir in parts:
            raise AssertionError(
                f"verifier boundary violated: gold test present in verifier workspace: {rel}"
            )
        if rel.name == _FIXER_ARTIFACT or "fixer" in parts or "patch" in parts:
            raise AssertionError(
                f"verifier boundary violated: fixer artifact in verifier workspace: {rel}"
            )


def _render_contract(contract: IssueContract, case: Case) -> str:
    lines = [f"Case: {case.id} - {case.title}", f"Summary: {contract.summary}"]
    if contract.invariants:
        lines.append("Invariants:")
        lines += [f"- {item}" for item in contract.invariants]
    if contract.inputs:
        lines.append("Inputs: " + ", ".join(contract.inputs))
    if contract.expected_outputs:
        lines.append("Expected outputs: " + ", ".join(contract.expected_outputs))
    if contract.out_of_scope:
        lines.append("Out of scope: " + ", ".join(contract.out_of_scope))
    if contract.ambiguities:
        lines.append("Ambiguities: " + ", ".join(contract.ambiguities))
    lines.append(f"Confidence: {contract.confidence.value}")
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    """Return the JSON body of a fenced reply (```json ... ```)."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    without_open = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    closing = without_open.rfind("```")
    return (without_open[:closing] if closing != -1 else without_open).strip()


def _parse_test(final_message: str, case: Case) -> VerifierTest:
    try:
        data = json.loads(_strip_code_fence(final_message))
    except json.JSONDecodeError as exc:
        raise VerifierError(
            f"verifier: model returned non-JSON output: {final_message[:200]!r}"
        ) from exc
    if not isinstance(data, dict):
        raise VerifierError(
            f"verifier: expected a JSON object, got {type(data).__name__}"
        )
    data["case_id"] = case.id
    try:
        return VerifierTest(**data)
    except ValidationError as exc:
        raise VerifierError(f"verifier: response failed schema validation: {exc}") from exc


def run_verifier(
    contract: IssueContract,
    case: Case,
    workspace: Workspace,
    client: ModelClient,
    settings: Settings,
    trace: Trace,
) -> VerifierTest:
    """Run the verifier agent loop on its own workspace and return a VerifierTest."""
    _assert_no_fixer_or_gold(workspace)

    system = _system_prompt() + "\n\n" + _render_contract(contract, case)
    result = run_agent(
        system,
        default_tools(),
        workspace,
        client,
        settings,
        trace,
        role="verifier",
    )
    test = _parse_test(result.final_message, case)

    trace.event(
        "verifier", "test",
        case_id=case.id,
        stop_reason=result.stop_reason,
        filename=test.filename,
        invariant=test.invariant,
        confidence=test.confidence.value,
        n_assumptions=len(test.assumptions),
        contents_len=len(test.contents),
    )
    return test
