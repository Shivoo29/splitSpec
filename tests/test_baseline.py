"""Baseline smoke check: the shared contracts and trace writer actually work."""
import json

from splitspec.config import ROOT, Settings
from splitspec.schemas import Case, RunResult, TestRun
from splitspec.trace import Trace


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("SPLITSPEC_MAX_TOKENS_PER_AGENT", "not-a-number")
    s = Settings.from_env()
    assert s.max_tokens_per_agent == 200_000  # bad value falls back, does not crash
    assert s.allow_cross_model_fallback is False  # cross-model failover is opt-in
    assert (ROOT / "splitspec").is_dir()


def test_providers_are_per_role(monkeypatch):
    monkeypatch.setenv("SPLITSPEC_FIXER_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("SPLITSPEC_FIXER_MODEL", "qwen3-32b")
    monkeypatch.setenv("SPLITSPEC_FIXER_API_KEYS", "k1, k2 ,")
    monkeypatch.setenv("SPLITSPEC_VERIFIER_BASE_URL", "https://gemini.example/v1")
    monkeypatch.setenv("SPLITSPEC_VERIFIER_MODEL", "gemini-flash-latest")
    monkeypatch.setenv("SPLITSPEC_VERIFIER_API_KEYS", "k3")
    for unset in ("SPLITSPEC_CONTRACT_BASE_URL", "SPLITSPEC_CONTRACT_MODEL"):
        monkeypatch.delenv(unset, raising=False)

    s = Settings.from_env()
    assert s.fixer.api_keys == ["k1", "k2"]  # several keys, one model: throughput only
    assert s.fixer.model != s.verifier.model
    assert s.contract.model == s.verifier.model  # unset contract role reuses the verifier
    assert "different models" in s.independence_note()
    assert "key" not in str(s.fixer.describe().get("model"))
    assert s.fixer.describe() == {
        "role": "fixer",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "qwen3-32b",
        "key_count": 2,
    }


def test_same_model_for_both_roles_is_flagged(monkeypatch):
    for role in ("FIXER", "VERIFIER"):
        monkeypatch.setenv(f"SPLITSPEC_{role}_BASE_URL", "https://one.example/v1")
        monkeypatch.setenv(f"SPLITSPEC_{role}_MODEL", "same-model")
        monkeypatch.setenv(f"SPLITSPEC_{role}_API_KEYS", "k")
    assert "procedural" in Settings.from_env().independence_note()


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
