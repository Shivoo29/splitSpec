"""Baseline smoke check: the shared contracts and trace writer actually work."""
import json

from splitspec.config import ROOT, Settings
from splitspec.schemas import Case, RunResult, TestRun
from splitspec.trace import Trace


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("SPLITSPEC_MODEL", raising=False)
    monkeypatch.setenv("SPLITSPEC_MAX_TOKENS_PER_AGENT", "not-a-number")
    s = Settings.from_env()
    assert s.model == "claude-sonnet-5"
    assert s.max_tokens_per_agent == 200_000  # bad value falls back, does not crash
    assert (ROOT / "splitspec").is_dir()


def test_schemas_roundtrip():
    case = Case(id="issue-07", title="Duplicate registration", issue_text="...")
    result = RunResult(case_id=case.id, mode="splitspec",
                       visible=TestRun(label="visible", command="pytest", passed=True, total=42))
    dumped = result.model_dump_json()
    assert RunResult.model_validate_json(dumped).visible.total == 42


def test_trace_appends(tmp_path):
    trace = Trace(tmp_path / "t.jsonl")
    trace.event("fixer", "tool_call", tool="read_file", path="app/main.py")
    trace.event("judge", "test_run", label="visible", passed=True)
    events = trace.read()
    assert [e["actor"] for e in events] == ["fixer", "judge"]
    assert json.loads(trace.path.read_text().splitlines()[0])["tool"] == "read_file"
