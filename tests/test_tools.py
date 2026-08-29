"""Module 5: agent tool loop tests.

The pure-loop tests drive a scripted :class:`FakeClient` — no network, no real
model — and run inside a host-only workspace. Tests that must execute ``pytest``
in the Docker sandbox are marked ``@pytest.mark.docker``.
"""
from __future__ import annotations

import json

import pytest
import yaml

from splitspec import sandbox
from splitspec.config import ROOT, Provider, Settings
from splitspec.llm import FakeClient, ModelReply, ToolCall
from splitspec.schemas import Case
from splitspec.tools import (
    STOP_BUDGET,
    STOP_EMPTY,
    STOP_FINISHED,
    STOP_LENGTH,
    default_tools,
    run_agent,
)
from splitspec.trace import Trace


def _settings(**overrides) -> Settings:
    def _p(role: str) -> Provider:
        return Provider(role=role, base_url=f"http://{role}.test", model="m")

    params: dict = dict(
        fixer=_p("fixer"),
        verifier=_p("verifier"),
        contract=_p("contract"),
    )
    params.update(overrides)
    return Settings(**params)


def _trace(tmp_path) -> Trace:
    return Trace(tmp_path / "trace.jsonl")


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


def _finish_call(summary: str = "done") -> ToolCall:
    return ToolCall(
        id="c-fin", name="finish", arguments=json.dumps({"summary": summary})
    )


def load_case(case_id: str) -> Case:
    data = yaml.safe_load((ROOT / "cases" / f"{case_id}.yaml").read_text())
    return Case.model_validate(data)


def _host_workspace(tmp_path) -> sandbox.Workspace:
    """A host-only workspace (no Docker) for pure-loop tests."""
    root = tmp_path / "ws"
    root.mkdir(parents=True, exist_ok=True)
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (root / "seed.py").write_text("SEED=1", encoding="utf-8")
    case = Case(id="t1", title="t", issue_text="x", fixture="eventpulse")
    return sandbox.Workspace(path=root, case_id="t1", role="fixer", case=case)


# ---------------------------------------------------------------------------


def test_normal_conversation_ends_when_tool_turn_followed_by_finish(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(tool_calls=[_finish_call("all good")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_FINISHED
    assert result.final_message == "all good"
    # the second reply (and later ones) are never consumed
    assert len(client.respond_calls) == 1


def test_path_escape_is_refused_and_loop_continues(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="read_file",
                        arguments=json.dumps({"path": "../outside.txt"}),
                    )
                ]
            ),
            _reply(tool_calls=[_finish_call("recovered")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    # The escape is reported to the model as a tool error and the loop continues.
    assert result.stop_reason == STOP_FINISHED
    assert result.final_message == "recovered"
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert any("path_escape" in m["content"] for m in tool_msgs)
    events = _trace(tmp_path).read()
    assert any(e["kind"] == "tool_error" and e["reason"] == "path_escape" for e in events)


def test_write_file_then_read_back_and_finish(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments=json.dumps(
                            {"path": "agent.txt", "content": "hello agent"}
                        ),
                    )
                ]
            ),
            _reply(tool_calls=[_finish_call("wrote it")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_FINISHED
    assert (ws.path / "agent.txt").read_text(encoding="utf-8") == "hello agent"


def test_fenced_json_arguments_are_parsed(tmp_path):
    ws = _host_workspace(tmp_path)
    finish = ToolCall(
        id="c-fin",
        name="finish",
        arguments="```json\n{\"summary\": \"fenced\"}\n```",
    )
    client = FakeClient(replies=[_reply(tool_calls=[finish])])
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_FINISHED
    assert result.final_message == "fenced"


def test_empty_reply_is_not_a_successful_finish(tmp_path):
    ws = _host_workspace(tmp_path)
    # Reasoning model spent its whole budget: HTTP 200 with no text and no tools.
    client = FakeClient(replies=[_reply(text="", finish_reason="stop")])
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_EMPTY
    events = _trace(tmp_path).read()
    assert any(e["kind"] == "agent_end" and e["stop_reason"] == STOP_EMPTY for e in events)


def test_length_reply_is_reported_as_truncation(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[_reply(text="partial answer...", finish_reason="length")]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_LENGTH
    assert result.final_message == "partial answer..."


def test_token_budget_cuts_the_loop_off(tmp_path):
    ws = _host_workspace(tmp_path)
    settings = _settings(max_tokens_per_agent=100)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[ToolCall(id="c1", name="list_files", arguments="{}")],
                input_tokens=60,
                output_tokens=60,
            ),
            _reply(tool_calls=[_finish_call("never reached")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, settings, _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_BUDGET
    # only the first reply was consumed before the budget check stopped the loop
    assert result.model_use.calls == 1
    events = _trace(tmp_path).read()
    assert any(e["kind"] == "budget" and e["reason"] == "budget_exceeded" for e in events)


def test_wall_clock_budget_cuts_the_loop_off(tmp_path):
    ws = _host_workspace(tmp_path)
    settings = _settings(agent_timeout_sec=90)
    clock_values = iter([0.0, 1000.0])
    client = FakeClient(
        replies=[
            _reply(tool_calls=[_finish_call("unreachable")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, settings, _trace(tmp_path), "fixer",
        clock=lambda: next(clock_values),
    )
    assert result.stop_reason == STOP_BUDGET
    events = _trace(tmp_path).read()
    assert any(e["kind"] == "budget" for e in events)


def test_run_tests_refuses_a_non_allowlisted_command(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="run_tests",
                        arguments=json.dumps({"command": ["ls", "-la"]}),
                    )
                ]
            ),
            _reply(tool_calls=[_finish_call("refused, recovered")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_FINISHED
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert any("refused" in m["content"] for m in tool_msgs)
    events = _trace(tmp_path).read()
    assert any(
        e["kind"] == "tool_error" and e["reason"] == "refused" for e in events
    )


def test_unknown_tool_reports_an_error_and_loop_continues(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(id="c1", name="rm_rf", arguments=json.dumps({"x": 1}))
                ]
            ),
            _reply(tool_calls=[_finish_call("after unknown tool")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_FINISHED
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert any("unknown_tool" in m["content"] for m in tool_msgs)
    assert result.final_message == "after unknown tool"


def test_bad_tool_arguments_are_reported_not_crashed(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(id="c1", name="read_file", arguments="{not json")
                ]
            ),
            _reply(tool_calls=[_finish_call("retried after bad json")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, _settings(), _trace(tmp_path), "fixer"
    )
    assert result.stop_reason == STOP_FINISHED
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert any("bad_args" in m["content"] for m in tool_msgs)


def test_every_model_and_tool_call_is_traced(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments=json.dumps(
                            {"path": "note.txt", "content": "hi"}
                        ),
                    )
                ],
                input_tokens=7,
                output_tokens=3,
            ),
            _reply(tool_calls=[_finish_call("done")]),
        ]
    )
    trace = _trace(tmp_path)
    run_agent("be a fixer", default_tools(), ws, client, _settings(), trace, "fixer")
    events = trace.read()
    model_calls = [e for e in events if e["kind"] == "model_call"]
    tool_calls = [e for e in events if e["kind"] == "tool_call"]
    assert len(model_calls) == 2
    # the write_file turn served 7/3 tokens; the finish turn served default 10/5
    assert {(e["input_tokens"], e["output_tokens"]) for e in model_calls} == {
        (7, 3),
        (10, 5),
    }
    assert {e["tool"] for e in tool_calls} >= {"write_file", "finish"}


def test_api_key_never_reaches_trace_or_model_use(tmp_path):
    ws = _host_workspace(tmp_path)
    settings = _settings(
        fixer=Provider(
            role="fixer",
            base_url="http://secret-host",
            model="m",
            api_keys=["SUPERSECRET"],
        )
    )
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call("ok")])])
    trace = _trace(tmp_path)
    result = run_agent(
        "be a fixer", default_tools(), ws, client, settings, trace, "fixer"
    )
    blob = json.dumps(result.model_use.model_dump())
    assert "SUPERSECRET" not in blob
    assert "SUPERSECRET" not in json.dumps(trace.read())


def test_model_use_totals_match_what_the_fake_client_served(tmp_path):
    ws = _host_workspace(tmp_path)
    settings = _settings(
        fixer=Provider(role="fixer", base_url="http://f", model="fixermodel")
    )
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[ToolCall(id="c1", name="list_files", arguments="{}")],
                input_tokens=100,
                output_tokens=50,
            ),
            _reply(input_tokens=80, output_tokens=20, tool_calls=[_finish_call("ok")]),
        ]
    )
    result = run_agent(
        "be a fixer", default_tools(), ws, client, settings, _trace(tmp_path), "fixer"
    )
    use = result.model_use
    assert use.role == "fixer"
    assert use.model == "fixermodel"
    assert use.base_url == "http://f"
    assert use.calls == 2
    assert use.input_tokens == 180
    assert use.output_tokens == 70


@pytest.mark.docker
def test_agent_runs_read_write_run_tests_finish_in_sandbox(tmp_path):
    case = load_case("issue-07")
    ws = sandbox.materialize(case, "fixer", tmp_path)
    try:
        client = FakeClient(
            replies=[
                _reply(
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="read_file",
                            arguments=json.dumps({"path": "README.md"}),
                        )
                    ]
                ),
                _reply(
                    tool_calls=[
                        ToolCall(
                            id="c2",
                            name="write_file",
                            arguments=json.dumps(
                                {"path": "agent.txt", "content": "hi"}
                            ),
                        )
                    ]
                ),
                _reply(
                    tool_calls=[
                        ToolCall(
                            id="c3",
                            name="run_tests",
                            arguments=json.dumps(
                                {"command": ["pytest", "-q", "-p", "no:cacheprovider"]}
                            ),
                        )
                    ]
                ),
                _reply(tool_calls=[_finish_call("all done")]),
            ]
        )
        settings = _settings(
            fixer=Provider(role="fixer", base_url="http://f", model="fm"),
            verifier=Provider(role="verifier", base_url="http://v", model="vm"),
        )
        result = run_agent(
            "be a fixer",
            default_tools(),
            ws,
            client,
            settings,
            Trace(tmp_path / "trace.jsonl"),
            "fixer",
        )
        assert result.stop_reason == STOP_FINISHED
        assert result.final_message == "all done"
        assert (ws.path / "agent.txt").read_text(encoding="utf-8") == "hi"
        tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
        assert any("exit=" in m["content"] for m in tool_msgs)
    finally:
        ws.destroy()


# --- Regressions from the first live run against real providers ---------------
#
# A FakeClient accepts any transcript, so neither of these could fail before.


def test_tool_results_are_preceded_by_the_assistant_turn(tmp_path):
    """OpenAI-compatible providers reject a tool result with no assistant turn
    carrying the same tool_call_id. Live, this 400s on the second request."""
    ws = _host_workspace(tmp_path)
    read = ToolCall(id="c-1", name="read_file", arguments=json.dumps({"path": "app/main.py"}))
    client = FakeClient(replies=[_reply(tool_calls=[read]), _reply(tool_calls=[_finish_call()])])

    result = run_agent(
        system_prompt="s", tools=default_tools(), workspace=ws, client=client,
        settings=_settings(), trace=_trace(tmp_path), role="fixer",
    )
    assert result.stop_reason == "finished"

    roles = [m["role"] for m in result.messages]
    tool_index = roles.index("tool")
    assert roles[tool_index - 1] == "assistant", f"transcript is malformed: {roles}"

    assistant = result.messages[tool_index - 1]
    ids = [tc["id"] for tc in assistant["tool_calls"]]
    assert result.messages[tool_index]["tool_call_id"] in ids


def test_providers_assistant_message_is_replayed_verbatim(tmp_path):
    """Gemini 3.x rejects a rebuilt function call that lost its thought_signature,
    so whatever the provider sent must go back unchanged."""
    ws = _host_workspace(tmp_path)
    read = ToolCall(id="c-1", name="read_file", arguments=json.dumps({"path": "app/main.py"}))
    raw = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "c-1",
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"path": "app/main.py"}'},
            "extra_content": {"thought_signature": "sig-abc123"},
        }],
    }
    reply = _reply(tool_calls=[read])
    reply.raw_message = raw
    client = FakeClient(replies=[reply, _reply(tool_calls=[_finish_call()])])

    result = run_agent(
        system_prompt="s", tools=default_tools(), workspace=ws, client=client,
        settings=_settings(), trace=_trace(tmp_path), role="fixer",
    )
    assistant = next(m for m in result.messages if m.get("role") == "assistant")
    assert assistant is raw or assistant == raw
    assert assistant["tool_calls"][0]["extra_content"]["thought_signature"] == "sig-abc123"


def test_per_reply_max_tokens_is_not_the_whole_run_budget(tmp_path):
    """max_tokens caps one reply. Sending the run budget (200k) makes providers
    refuse the request outright -- Groq's free tier answers HTTP 413."""
    ws = _host_workspace(tmp_path)
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call()])])
    settings = _settings()

    run_agent(
        system_prompt="s", tools=default_tools(), workspace=ws, client=client,
        settings=settings, trace=_trace(tmp_path), role="fixer",
    )
    asked = client.respond_calls[0]["max_tokens"]
    assert asked < settings.max_tokens_per_agent
    assert asked <= 8000
