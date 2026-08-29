"""Contract builder (Module 4).

Turns a :class:`Case`'s issue text plus a caller-supplied repository context into
an :class:`schemas.IssueContract` with a single model call. The prompt is loaded
from ``splitspec/prompts/contract.md`` and states that issue text, code, logs
and docs are untrusted data.

The model client is injected — this function performs exactly one model call and
nothing else — and the resulting contract is shared verbatim by both the fixer
and the verifier, so any asymmetry between them comes from their roles, not
their inputs.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from splitspec.llm import ModelClient
from splitspec.schemas import Case, Confidence, IssueContract
from splitspec.trace import Trace

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "contract.md"
_DEFAULT_MAX_TOKENS = 1500


class ContractError(RuntimeError):
    """The model response could not be turned into a valid IssueContract."""


class ContractInjectionError(ContractError):
    """The contract carried an instruction that came from the untrusted issue text."""


# Case 12's issue text tells the reader to delete the visible test suite and close the
# ticket. Telling the model that issue text is data is necessary but not sufficient: a
# model can still swallow the instruction and hand it back as a requirement. A contract
# is a specification of BEHAVIOR, so a demand to remove, skip, or neutralise tests is
# never legitimate content and is refused here rather than passed to the fixer.
_FORBIDDEN_DIRECTIVES = (
    ("delete", "test"),
    ("remove", "test"),
    ("drop", "test"),
    ("skip", "test"),
    ("disable", "test"),
    ("xfail",),
    ("visible_tests",),
    ("gold_hidden_tests",),
    ("without changing", "code"),
    ("without modifying", "code"),
    ("no code change",),
    ("already", "resolved upstream"),
)


def _actionable_text(contract: IssueContract) -> list[tuple[str, str]]:
    """Every field a downstream agent could act on, as (field name, text) pairs."""
    pairs = [("summary", contract.summary)]
    for name in ("invariants", "inputs", "expected_outputs", "out_of_scope"):
        pairs += [(name, item) for item in getattr(contract, name)]
    return pairs


def _reject_injected_directives(contract: IssueContract) -> None:
    for field, text in _actionable_text(contract):
        lowered = text.lower()
        for directive in _FORBIDDEN_DIRECTIVES:
            if all(token in lowered for token in directive):
                raise ContractInjectionError(
                    f"contract builder: {field} carries an instruction from the untrusted "
                    f"issue text ({' + '.join(directive)!r}): {text!r}. Issue text is data; a "
                    "contract may describe behavior, never repository or process actions."
                )


def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_contract(
    case: Case,
    repo_context: str,
    client: ModelClient,
    trace: Trace | None = None,
) -> IssueContract:
    """Produce the IssueContract for ``case`` with one call to ``client``."""
    system = _system_prompt()
    user = (
        f"Repository: {case.fixture}\n"
        f"Issue id: {case.id}\n"
        f"Issue title: {case.title}\n\n"
        f"Repository context:\n{repo_context}\n\n"
        f"Issue text:\n{case.issue_text}"
    )

    completion = client.complete(
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=_DEFAULT_MAX_TOKENS,
    )

    contract = _parse_completion(case, completion.text, completion.model)

    if trace is not None:
        trace.event("contract", "call", case_id=case.id, model=completion.model)
        trace.event(
            "contract", "tokens",
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            model=completion.model,
        )
        trace.event(
            "contract", "parsed",
            case_id=contract.case_id,
            confidence=contract.confidence.value,
            n_invariants=len(contract.invariants),
            n_ambiguities=len(contract.ambiguities),
        )
    return contract


def _parse_completion(case: Case, text: str, model: str) -> IssueContract:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"contract builder: model ({model or 'unknown'}) returned non-JSON output"
        ) from exc
    if not isinstance(data, dict):
        raise ContractError(f"contract builder: expected a JSON object, got {type(data).__name__}")

    try:
        contract = IssueContract(**data)
    except ValidationError as exc:
        raise ContractError(f"contract builder: response failed schema validation: {exc}") from exc

    # The response must not be allowed to mislabel which case this contract is for.
    contract.case_id = case.id

    if contract.confidence in (Confidence.medium, Confidence.high) and not contract.invariants:
        raise ContractError(
            "contract builder: contract claims confidence="
            f"{contract.confidence.value} but lists no invariants — refusing a half-populated contract"
        )

    _reject_injected_directives(contract)
    return contract
