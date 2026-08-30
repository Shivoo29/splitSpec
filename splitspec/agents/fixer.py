"""Fixer agent (Module 6).

Wraps the shared Module 5 tool loop into a fixer-specific `Patch` producer. It
receives the same `IssueContract` the verifier gets (so any asymmetry between the
two agents comes from their roles, not their inputs) and returns a
:class:`~splitspec.schemas.Patch`.

The patch's metadata (`files_changed`, `lines_added`, `lines_removed`,
`touched_tests`) is computed **from the workspace's actual diff** — never from
what the model claims in its final message. A fixer that says it only touched a
route while editing a test is still recorded with `touched_tests=True`.

`touched_tests` means an EXISTING test was changed. Adding a regression test is
explicitly permitted by the fixer instruction, so a new test file is not a
violation and must not be reported as one.

The information boundary is enforced at entry: the fixer workspace must contain no
gold test and no verifier artifact. Because a leak invalidates the whole
experiment this is a hard assertion that raises immediately, not a log line.
"""
from __future__ import annotations

from pathlib import Path

from splitspec.config import GOLD_TESTS_DIR, Settings
from splitspec.llm import ModelClient
from splitspec.sandbox import Workspace
from splitspec.schemas import Case, IssueContract, Patch
from splitspec.tools import STOP_FINISHED, default_tools, run_agent
from splitspec.trace import Trace

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "fixer.md"

# The frozen verifier test is written to disk under this name (PROJECT.md §13).
_VERIFIER_ARTIFACT = "verifier_test.py"


def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _assert_no_gold_or_verifier(workspace: Workspace) -> None:
    """Hard boundary: no gold test and no verifier artifact inside the workspace."""
    gold_dir = GOLD_TESTS_DIR.name
    for path in sorted(Path(workspace.path).rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(workspace.path)
        parts = set(rel.parts)
        if gold_dir in parts:
            raise AssertionError(
                f"fixer boundary violated: gold test present in fixer workspace: {rel}"
            )
        if rel.name == _VERIFIER_ARTIFACT or "verifier" in parts:
            raise AssertionError(
                f"fixer boundary violated: verifier artifact in fixer workspace: {rel}"
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


def _diff_meta(diff: str) -> tuple[list[str], int, int]:
    """(files_changed, lines_added, lines_removed) parsed from a unified diff."""
    files: list[str] = []
    added = 0
    removed = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[len("+++ b/"):])
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return files, added, removed


def _is_test(rel: str) -> bool:
    parts = Path(rel).parts
    return "visible_tests" in parts or Path(rel).name.startswith("test_")


def _modified_existing_tests(diff: str, workspace: Workspace) -> list[str]:
    """Test files the patch CHANGED, as opposed to test files it added.

    The fixer instruction permits adding tests and forbids weakening existing ones,
    and Module 11 rejects a patch on `touched_tests`. Conflating the two would auto
    reject a fixer that did the right thing and wrote a regression test, while case
    10 needs the genuine article - an edited expectation - to still be caught.
    """
    touched: list[str] = []
    for line in diff.splitlines():
        if not line.startswith("+++ b/"):
            continue
        rel = line[len("+++ b/"):]
        if not _is_test(rel):
            continue
        # `materialize` recorded the as-materialized tree; a path that exists in the
        # baseline and appears in the diff was modified, not created.
        if rel in workspace.baseline_files():
            touched.append(rel)
    return touched


#: Notes are a human-readable label on the patch, not a transcript. A model that
#: degenerates into a repetition loop and stops on `length` returns its entire
#: 8000-token reply as the final message; storing that verbatim put 39k characters
#: into result.json, the review packet, the dashboard, and the operator's terminal.
#: The full reply is already in trajectory.jsonl, which is where a transcript belongs.
_MAX_NOTE_CHARS = 600


def _notes(stop_reason: str, final_message: str) -> str:
    note = f"stop_reason={stop_reason}"
    message = " ".join(final_message.split())
    if message:
        if len(message) > _MAX_NOTE_CHARS:
            message = (
                f"{message[:_MAX_NOTE_CHARS]}... "
                f"[truncated, {len(final_message)} chars; full reply in trajectory.jsonl]"
            )
        note += f"; {message}"
    return note


def run_fixer(
    contract: IssueContract,
    case: Case,
    workspace: Workspace,
    client: ModelClient,
    settings: Settings,
    trace: Trace,
) -> Patch:
    """Run the fixer agent loop and produce a :class:`Patch`."""
    _assert_no_gold_or_verifier(workspace)

    system = _system_prompt() + "\n\n" + _render_contract(contract, case)
    result = run_agent(
        system,
        default_tools(),
        workspace,
        client,
        settings,
        trace,
        role="fixer",
    )

    diff = workspace.snapshot_diff()
    files, added, removed = _diff_meta(diff)
    patch = Patch(
        case_id=case.id,
        diff=diff,
        files_changed=files,
        lines_added=added,
        lines_removed=removed,
        touched_tests=bool(_modified_existing_tests(diff, workspace)),
        notes=_notes(result.stop_reason, result.final_message),
    )

    trace.event(
        "fixer", "patch",
        case_id=case.id,
        stop_reason=result.stop_reason,
        stop_ok=result.stop_reason == STOP_FINISHED,
        files=files,
        lines_added=added,
        lines_removed=removed,
        touched_tests=patch.touched_tests,
        diff_len=len(diff),
    )
    return patch
