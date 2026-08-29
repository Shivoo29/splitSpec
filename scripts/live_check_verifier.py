"""Live end-to-end check of the verifier agent on issue-07 (Module 7).

This is NOT a unit test: it drives the real configured verifier model against a
materialized buggy workspace, then freezes and gates the produced test. Run it by
hand when a verifier model is configured in `.env`:

    .venv/bin/python scripts/live_check_verifier.py

It loads `SPLITSPEC_*` from `.env` (stdlib parse; no dotenv dependency) and prints
a PASS/FAIL confirmation for every invariant the project doc asks for:

- the generated test file actually imports and runs,
- fails_on_original_bug is True for a genuine test and the gate rejects a test that passes,
- the stated invariant resembles "at most one registration per (user, event)",
- the frozen sha256 changes if you edit the file and load_frozen then raises,
- no gold_hidden path appears anywhere in the verifier's trace (grep count == 0).

No secrets are written anywhere: the API keys are read from the environment only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitspec import sandbox  # noqa: E402
from splitspec.agents.verifier import VerifierError, run_verifier  # noqa: E402
from splitspec.config import Settings, load_dotenv  # noqa: E402
from splitspec.contracts import build_contract  # noqa: E402
from splitspec.freeze import VERIFIER_TEST_FILENAME, freeze, load_frozen  # noqa: E402
from splitspec.gate import gate  # noqa: E402
from splitspec.llm import OpenAICompatibleClient  # noqa: E402
from splitspec.schemas import Case, Confidence, VerifierTest  # noqa: E402
from splitspec.trace import Trace  # noqa: E402

CASE_ID = "issue-07"


def load_env() -> None:
    """Load .env via the single loader in config, so script and CLI agree."""
    if not (ROOT / ".env").is_file():
        print("WARN: no .env found; assuming SPLITSPEC_* are already exported.")
    load_dotenv()


def repo_context(case: Case) -> str:
    """A flat, sorted text snapshot of the fixture the contract builder reads."""
    base = Path(ROOT) / "fixtures" / case.fixture
    app = base / "app"
    lines: list[str] = []
    for path in sorted(app.rglob("*.py")):
        rel = path.relative_to(base).as_posix()
        lines.append(f"===== {rel} =====")
        lines.append(path.read_text(encoding="utf-8"))
    for name in ("seed.py", "conftest.py"):
        p = base / name
        if p.is_file():
            lines.append(f"===== {name} =====")
            lines.append(p.read_text(encoding="utf-8"))
    return "\n".join(lines)


def main() -> int:
    load_env()
    settings = Settings.from_env()
    verifier = settings.provider("verifier")
    if not verifier.configured:
        print(
            "NOT CONFIGURED: SPLITSPEC_VERIFIER_* is not set. "
            "Set it in .env to run the live check."
        )
        return 2

    print(f"verifier model: {verifier.model} @ {verifier.base_url}")
    print(f"independence: {settings.independence_note()}")

    case = Case.model_validate(_load_case_yaml())

    out: Path = ROOT / "artifacts" / "live-check-issue-07"
    out.mkdir(parents=True, exist_ok=True)
    verifier_trace = Trace(out / "trace.jsonl")

    client = OpenAICompatibleClient(
        verifier,
        max_retries=settings.max_retries,
        retry_base_delay_sec=settings.retry_base_delay_sec,
    )

    contract = build_contract(case, repo_context(case), client, trace=verifier_trace)
    print("\n--- contract ---")
    print(f"summary: {contract.summary}")
    print(f"invariants: {contract.invariants}")
    print(f"confidence: {contract.confidence.value}")

    print("\n--- verifier run (real model, may take a while) ---")
    verifier_ws = sandbox.materialize(case, "verifier", out)
    recovered = False
    test: VerifierTest | None = None
    try:
        try:
            test = run_verifier(contract, case, verifier_ws, client, settings, verifier_trace)
        except VerifierError as exc:
            # Diagnostic fallback (not a pipeline change): if the model exhausted
            # its budget/turn without emitting the final JSON, recover the last
            # test file it actually WROTE into its own workspace so we can still
            # demonstrate freeze + gate on a real model-authored artifact.
            print(f"run_verifier yielded no JSON ({exc}); trying workspace recovery")
            test = _recover_workspace_test(verifier_ws, case)
            if test is None:
                raise
            recovered = True
    finally:
        verifier_ws.destroy()

    print(
        f"stop: filename={test.filename!r} confidence={test.confidence.value} "
        f"(recovered_from_workspace={recovered})"
    )
    print(f"invariant: {test.invariant!r}")
    print(f"run_command: {test.run_command!r}")
    print(f"n_assumptions: {len(test.assumptions)}")
    print("--- generated test ---")
    print(test.contents)

    # --- freeze + sha integrity -------------------------------------------
    frozen = freeze(test, out)
    print(f"\nfrozen sha256: {frozen.frozen_sha256}")
    _assert(
        len(frozen.frozen_sha256) == 64, "frozen_sha256 is a 64-hex sha256"
    )

    # edit the file and confirm load_frozen raises
    test_path = out / VERIFIER_TEST_FILENAME
    _chmod_writable(test_path)
    test_path.write_text(test.contents + "\n# tampered\n", encoding="utf-8")
    try:
        load_frozen(out)
        _assert(False, "load_frozen raised on tampered file")
    except RuntimeError as exc:
        print(f"load_frozen raised as expected on tamper: {exc}")
        _assert(True, "load_frozen raises after the file is edited")
    # restore
    _chmod_writable(test_path)
    test_path.write_text(test.contents, encoding="utf-8")
    restored = load_frozen(out)
    _assert(restored == frozen, "load_frozen round-trips the frozen test")

    # --- gate the generated test against the BUGGY code --------------------
    print("\n--- gate: generated test vs original buggy code ---")
    v_gate = gate(frozen, case, out / "gate_valid", verifier_trace)
    print(v_gate.model_dump())
    _assert(v_gate.runs is True, "generated test ran (imported+executed)")
    _assert(
        v_gate.fails_on_original_bug is True,
        "fails_on_original_bug is True for a genuine test",
    )
    _assert(v_gate.passed is True, "gate passed for a genuine test")

    # --- gate rejects a test that passes on the buggy code ------------------
    print("\n--- gate: a deliberately passing test (sanity) vs buggy code ---")
    passing = VerifierTest(
        case_id=case.id,
        filename="test_trivially_passes.py",
        contents="def test_trivial():\n    assert True\n",
        run_command="pytest test_trivially_passes.py",
        invariant="trivial",
        assumptions=[],
    )
    p_gate = gate(passing, case, out / "gate_pass", verifier_trace)
    print(p_gate.model_dump())
    _assert(p_gate.runs is True, "passing test ran")
    _assert(p_gate.fails_on_original_bug is False, "passing test does not catch the bug")
    _assert(p_gate.passed is False, "gate rejects a test that passes on the bug")
    _assert(
        p_gate.reason and "not discriminating" in p_gate.reason,
        "gate records a reason for the invalid test",
    )

    # --- invariant resemblance ---------------------------------------------
    _assert(
        _resembles_uniqueness(test.invariant),
        "invariant resembles 'at most one registration per (user, event)'",
    )

    # --- no gold path in the verifier trace --------------------------------
    gold_refs = _count_gold_refs(verifier_trace)
    print(f"\ngold_hidden references in trace.jsonl: {gold_refs}")
    _assert(gold_refs == 0, "no gold_hidden path appears in the verifier trace")

    print("\nALL CHECKS PASSED")
    return 0


def _load_case_yaml() -> dict:
    """Load a case YAML via pyyaml (an installed dependency), returning dict."""
    import yaml

    return yaml.safe_load((ROOT / "cases" / f"{CASE_ID}.yaml").read_text(encoding="utf-8"))


def _recover_workspace_test(ws: sandbox.Workspace, case: Case) -> VerifierTest | None:
    """Return the last test_*.py the verifier wrote to its workspace root.

    Ignore anything under visible_tests/ (that is seeded fixture, not the verifier's
    own artifact). None if the model wrote no such file.
    """
    ws_root = Path(ws.path)
    vis = (ws_root / "visible_tests").resolve()
    candidates: list[tuple[float, Path]] = []
    for path in ws_root.rglob("test_*.py"):
        if vis in path.resolve().parents:
            continue
        candidates.append((path.stat().st_mtime, path))
    if not candidates:
        return None
    _, latest = max(candidates, key=lambda pair: pair[0])
    return VerifierTest(
        case_id=case.id,
        filename=latest.name,
        contents=latest.read_text(encoding="utf-8"),
        run_command=f"pytest {latest.name}",
        invariant="(recovered from verifier workspace; invariant not stated in JSON)",
        assumptions=[],
        confidence=Confidence.medium,
    )


def _count_gold_refs(trace: Trace) -> int:
    try:
        text = trace.path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return 0
    return text.lower().count("gold_hidden")


def _resembles_uniqueness(invariant: str) -> bool:
    tokens = ("one", "1", "single", "unique", "duplicate", "once", "at most", "per (user, event)")
    return any(t in invariant.lower() for t in tokens)


def _chmod_writable(path: Path) -> None:
    os.chmod(path, 0o644)


def _assert(cond: bool, label: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        print("ABORTING: a check failed.")
        sys.exit(1)


if __name__ == "__main__":
    raise SystemExit(main())
