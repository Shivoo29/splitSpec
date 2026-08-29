"""Module 7: verifier agent tests.

Pure-loop tests drive a scripted :class:`FakeClient` (no network) against a
host-only workspace. They assert the verifier produces a valid
:class:`VerifierTest`, that the information boundary fires before any model call,
and that the flood/parse path raises :class:`VerifierError` on malformed output.
"""
from __future__ import annotations

import json

import pytest
import yaml

from splitspec import sandbox
from splitspec.agents.verifier import VerifierError, run_verifier
from splitspec.config import ROOT, Provider, Settings
from splitspec.llm import FakeClient, ModelReply, ToolCall
from splitspec.schemas import Case, Confidence, IssueContract, VerifierTest
from splitspec.trace import Trace


def _settings(**overrides) -> Settings:
    def _p(role: str) -> Provider:
        return Provider(role=role, base_url=f"http://{role}.test", model="m")

    params: dict = dict(fixer=_p("fixer"), verifier=_p("verifier"), contract=_p("contract"))
    params.update(overrides)
    return Settings(**params)


def load_case(case_id: str) -> Case:
    data = yaml.safe_load((ROOT / "cases" / f"{case_id}.yaml").read_text())
    return Case.model_validate(data)


def _contract(case: Case) -> IssueContract:
    return IssueContract(
        case_id=case.id,
        summary="Reject empty titles and negative prices at create time.",
        invariants=["An event with an empty title is rejected before it is stored."],
        confidence=Confidence.high,
    )


def _reply(
    text: str = "",
    tool_calls: list[ToolCall] | None = None,
    finish_reason: str = "tool_calls",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> ModelReply:
    return ModelReply(
        text=text,
        tool_calls=tool_calls or [],
        finish_reason=finish_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model="m",
    )


def _finish_call(payload: str) -> ToolCall:
    return ToolCall(id="c-fin", name="finish", arguments=json.dumps({"summary": payload}))


def _valid_test_json(case_id: str = "issue-01") -> str:
    obj = {
        "filename": "test_verifier_probe.py",
        "contents": "def test_empty_title_rejected():\n    assert True\n",
        "run_command": "pytest test_verifier_probe.py",
        "invariant": "empty titles are rejected before storage",
        "assumptions": ["the API requires auth"],
        "confidence": "high",
    }
    return "```json\n" + json.dumps(obj) + "\n```"


def _host_workspace(tmp_path, case_id: str = "issue-01") -> sandbox.Workspace:
    root = tmp_path / "ws"
    (root / "app" / "routes").mkdir(parents=True, exist_ok=True)
    (root / "app" / "routes" / "events.py").write_text("", encoding="utf-8")
    vis = root / "visible_tests" / case_id
    vis.mkdir(parents=True, exist_ok=True)
    (vis / "test_events.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (root / "seed.py").write_text("SEED=1", encoding="utf-8")
    case = Case(id=case_id, title="t", issue_text="x", fixture="eventpulse")
    return sandbox.Workspace(path=root, case_id=case_id, role="verifier", case=case)


def test_scripted_verifier_produces_valid_test(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(tool_calls=[_finish_call(_valid_test_json())]),
        ]
    )
    test = run_verifier(
        _contract(load_case("issue-01")),
        load_case("issue-01"),
        ws,
        client,
        _settings(),
        Trace(tmp_path / "trace.jsonl"),
    )
    assert isinstance(test, VerifierTest)
    assert test.case_id == "issue-01"
    assert test.filename == "test_verifier_probe.py"
    assert test.run_command == "pytest test_verifier_probe.py"
    assert test.invariant
    assert test.assumptions == ["the API requires auth"]
    assert test.confidence == Confidence.high
    assert "test_empty_title_rejected" in test.contents
    assert test.frozen_sha256 == ""


def test_verifier_writes_verifier_test_event_to_trace(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call(_valid_test_json())])])
    trace = Trace(tmp_path / "trace.jsonl")
    run_verifier(
        _contract(load_case("issue-01")),
        load_case("issue-01"),
        ws,
        client,
        _settings(),
        trace,
    )
    events = trace.read()
    assert any(e["kind"] == "test" and e["actor"] == "verifier" for e in events)


def test_verifier_receives_identical_contract_object(tmp_path):
    ws = _host_workspace(tmp_path)
    contract = _contract(load_case("issue-01"))
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call(_valid_test_json())])])
    run_verifier(
        contract,
        load_case("issue-01"),
        ws,
        client,
        _settings(),
        Trace(tmp_path / "trace.jsonl"),
    )
    # The verifier's system prompt embeds the very contract the fixer received,
    # so the boundary is about the identity of what is asked, not a re-derivation.
    sys_prompt = client.respond_calls[0]["system"]
    assert "Reject empty titles and negative prices at create time." in sys_prompt
    assert "An event with an empty title is rejected before it is stored." in sys_prompt


def test_planting_gold_test_triggers_boundary_assertion(tmp_path):
    ws = _host_workspace(tmp_path)
    gold = ws.path / "gold_hidden_tests" / "issue-01"
    gold.mkdir(parents=True)
    (gold / "test_hidden.py").write_text("def test_hidden():\n    assert False\n", encoding="utf-8")
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call(_valid_test_json())])])
    with pytest.raises(AssertionError, match="gold"):
        run_verifier(
            _contract(load_case("issue-01")),
            load_case("issue-01"),
            ws,
            client,
            _settings(),
            Trace(tmp_path / "trace.jsonl"),
        )
    assert client.respond_calls == []


def test_planting_fixer_patch_triggers_boundary_assertion(tmp_path):
    ws = _host_workspace(tmp_path)
    (ws.path / "fixer_patch.diff").write_text("--- a/x\n+++ b/x\n", encoding="utf-8")
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call(_valid_test_json())])])
    with pytest.raises(AssertionError, match="patch"):
        run_verifier(
            _contract(load_case("issue-01")),
            load_case("issue-01"),
            ws,
            client,
            _settings(),
            Trace(tmp_path / "trace.jsonl"),
        )
    assert client.respond_calls == []


def test_non_json_final_message_raises_verifier_error(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call("sorry, no test")])])
    with pytest.raises(VerifierError, match="non-JSON"):
        run_verifier(
            _contract(load_case("issue-01")),
            load_case("issue-01"),
            ws,
            client,
            _settings(),
            Trace(tmp_path / "trace.jsonl"),
        )


def test_schema_invalid_final_message_raises_verifier_error(tmp_path):
    ws = _host_workspace(tmp_path)
    # Missing required keys (filename, contents, ...).
    bad = json.dumps({"filename": "test_x.py"})
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call(bad)])])
    with pytest.raises(VerifierError, match="validation"):
        run_verifier(
            _contract(load_case("issue-01")),
            load_case("issue-01"),
            ws,
            client,
            _settings(),
            Trace(tmp_path / "trace.jsonl"),
        )
