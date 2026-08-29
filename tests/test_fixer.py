"""Module 6: fixer agent tests.

Pure-loop tests drive a scripted :class:`FakeClient` (no network) against a
host-only workspace. The single sandbox test applies the produced patch in a
fresh judge workspace and is marked ``@pytest.mark.docker``.
"""
from __future__ import annotations

import json

import pytest
import yaml

from splitspec import sandbox
from splitspec.agents.fixer import run_fixer
from splitspec.config import ROOT, Provider, Settings
from splitspec.llm import FakeClient, ModelReply, ToolCall
from splitspec.schemas import Case, Confidence, IssueContract
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


def _finish_call(summary: str) -> ToolCall:
    return ToolCall(id="c-fin", name="finish", arguments=json.dumps({"summary": summary}))


EVENTS_PATH = "app/routes/events.py"


def _orig_events() -> str:
    return (ROOT / "fixtures" / "eventpulse" / EVENTS_PATH).read_text(encoding="utf-8")


def _host_workspace(tmp_path, case_id: str = "issue-01") -> sandbox.Workspace:
    root = tmp_path / "ws"
    (root / EVENTS_PATH).parent.mkdir(parents=True, exist_ok=True)
    # normalize a trailing newline so a one-line append reads as a clean addition
    (root / EVENTS_PATH).write_text(_orig_events().rstrip("\n") + "\n", encoding="utf-8")
    vis = root / "visible_tests" / case_id
    vis.mkdir(parents=True, exist_ok=True)
    (vis / "test_events.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (root / "seed.py").write_text("SEED=1", encoding="utf-8")
    case = Case(id=case_id, title="t", issue_text="x", fixture="eventpulse")
    return sandbox.Workspace(path=root, case_id=case_id, role="fixer", case=case)


# ---------------------------------------------------------------------------


def test_edit_events_yields_nonempty_diff_with_correct_metadata(tmp_path):
    ws = _host_workspace(tmp_path)
    new_events = _orig_events() + "\n# fixer note: validation tightened\n"
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments=json.dumps(
                            {"path": EVENTS_PATH, "content": new_events}
                        ),
                    )
                ]
            ),
            _reply(tool_calls=[_finish_call("edited events.py")]),
        ]
    )
    patch = run_fixer(
        _contract(load_case("issue-01")),
        load_case("issue-01"),
        ws,
        client,
        _settings(),
        Trace(tmp_path / "trace.jsonl"),
    )
    assert patch.case_id == "issue-01"
    assert patch.diff  # non-empty
    assert EVENTS_PATH in patch.files_changed
    assert patch.lines_added >= 1
    assert patch.lines_removed == 0
    assert patch.touched_tests is False
    assert patch.notes.startswith("stop_reason=finished")


def test_editing_visible_test_sets_touched_tests_even_if_message_claims_otherwise(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments=json.dumps(
                            {
                                "path": "visible_tests/issue-01/test_events.py",
                                "content": "def test_weakened():\n    pass\n",
                            }
                        ),
                    )
                ]
            ),
            # The model's final text claims it only touched the route.
            _reply(tool_calls=[_finish_call("I only changed the route, no tests touched")]),
        ]
    )
    patch = run_fixer(
        _contract(load_case("issue-01")),
        load_case("issue-01"),
        ws,
        client,
        _settings(),
        Trace(tmp_path / "trace.jsonl"),
    )
    assert patch.touched_tests is True
    assert any("test_events.py" in f for f in patch.files_changed)


def test_planting_gold_test_triggers_boundary_assertion(tmp_path):
    ws = _host_workspace(tmp_path)
    gold = ws.path / "gold_hidden_tests" / "issue-01"
    gold.mkdir(parents=True)
    (gold / "test_hidden.py").write_text("def test_hidden():\n    assert False\n", encoding="utf-8")
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call("done")])])
    with pytest.raises(AssertionError, match="gold"):
        run_fixer(
            _contract(load_case("issue-01")),
            load_case("issue-01"),
            ws,
            client,
            _settings(),
            Trace(tmp_path / "trace.jsonl"),
        )
    # the boundary fired before any model call
    assert client.respond_calls == []


def test_planting_verifier_artifact_triggers_boundary_assertion(tmp_path):
    ws = _host_workspace(tmp_path)
    (ws.path / "verifier_test.py").write_text("def test_v():\n    pass\n", encoding="utf-8")
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call("done")])])
    with pytest.raises(AssertionError, match="verifier"):
        run_fixer(
            _contract(load_case("issue-01")),
            load_case("issue-01"),
            ws,
            client,
            _settings(),
            Trace(tmp_path / "trace.jsonl"),
        )
    assert client.respond_calls == []


def test_budget_stop_is_recorded_in_patch_notes(tmp_path):
    ws = _host_workspace(tmp_path)
    new_events = _orig_events() + "\n# partial\n"
    settings = _settings(max_tokens_per_agent=100)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="write_file",
                        arguments=json.dumps(
                            {"path": EVENTS_PATH, "content": new_events}
                        ),
                    )
                ],
                input_tokens=60,
                output_tokens=60,
            ),
            _reply(tool_calls=[_finish_call("should never be reached")]),
        ]
    )
    patch = run_fixer(
        _contract(load_case("issue-01")),
        load_case("issue-01"),
        ws,
        client,
        settings,
        Trace(tmp_path / "trace.jsonl"),
    )
    assert "budget" in patch.notes
    assert patch.notes.startswith("stop_reason=budget")
    # whatever diff existed before the cutoff is preserved, not discarded
    assert patch.diff
    assert EVENTS_PATH in patch.files_changed


def test_empty_diff_is_returned_as_empty_not_error(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(
        replies=[
            _reply(
                tool_calls=[
                    ToolCall(id="c1", name="list_files", arguments=json.dumps({"path": "."}))
                ]
            ),
            _reply(tool_calls=[_finish_call("no change needed")]),
        ]
    )
    patch = run_fixer(
        _contract(load_case("issue-01")),
        load_case("issue-01"),
        ws,
        client,
        _settings(),
        Trace(tmp_path / "trace.jsonl"),
    )
    assert patch.diff == ""
    assert patch.files_changed == []
    assert patch.lines_added == 0 and patch.lines_removed == 0
    assert patch.touched_tests is False
    assert patch.notes.startswith("stop_reason=finished")


def test_fixer_writes_patch_event_to_trace(tmp_path):
    ws = _host_workspace(tmp_path)
    client = FakeClient(replies=[_reply(tool_calls=[_finish_call("done")])])
    trace = Trace(tmp_path / "trace.jsonl")
    run_fixer(
        _contract(load_case("issue-01")),
        load_case("issue-01"),
        ws,
        client,
        _settings(),
        trace,
    )
    kinds = [e["kind"] for e in trace.read()]
    assert "patch" in kinds


@pytest.mark.docker
def test_fixer_patch_applies_cleanly_in_fresh_judge_workspace(tmp_path):
    case = load_case("issue-01")
    fixer_ws = sandbox.materialize(case, "fixer", tmp_path / "fixer")
    judge_ws = sandbox.materialize(case, "judge", tmp_path / "judge")
    try:
        orig = (fixer_ws.path / EVENTS_PATH).read_text(encoding="utf-8")
        new_events = orig + "\n# fixer edit applied in sandbox\n"
        client = FakeClient(
            replies=[
                _reply(
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="write_file",
                            arguments=json.dumps(
                                {"path": EVENTS_PATH, "content": new_events}
                            ),
                        )
                    ]
                ),
                _reply(tool_calls=[_finish_call("tightened validation")]),
            ]
        )
        patch = run_fixer(
            _contract(case),
            case,
            fixer_ws,
            client,
            _settings(),
            Trace(tmp_path / "trace.jsonl"),
        )
        assert patch.diff
        # the patch applies cleanly (no exception) to a fresh judge workspace
        # and carries the edit into the new file
        judge_ws.apply_patch(patch.diff)
        applied = (judge_ws.path / EVENTS_PATH).read_text(encoding="utf-8")
        assert "# fixer edit applied in sandbox" in applied
    finally:
        fixer_ws.destroy()
        judge_ws.destroy()


# --- Regressions from the first live fixer run --------------------------------


def test_adding_a_new_test_is_not_touching_tests(tmp_path):
    """The fixer instruction permits adding tests. Only editing an EXISTING one is a
    violation, and Module 11 rejects on this flag, so conflating them would auto
    reject a fixer that wrote a regression test."""
    ws = _host_workspace(tmp_path)
    _c = Case(id='issue-01', title='t', issue_text='x', fixture='eventpulse')
    write = ToolCall(
        id="c-1", name="write_file",
        arguments=json.dumps({"path": "test_regression.py", "content": "def test_x():\n    assert True\n"}),
    )
    client = FakeClient(replies=[_reply(tool_calls=[write]), _reply(tool_calls=[_finish_call("done")])])

    patch = run_fixer(_contract(_c), _c, ws, client, _settings(), Trace(tmp_path / 'tr.jsonl'))
    assert "test_regression.py" in patch.files_changed
    assert patch.touched_tests is False


def test_editing_an_existing_visible_test_is_touching_tests(tmp_path):
    ws = _host_workspace(tmp_path)
    _c = Case(id='issue-01', title='t', issue_text='x', fixture='eventpulse')
    edit = ToolCall(
        id="c-1", name="write_file",
        arguments=json.dumps({
            "path": "visible_tests/issue-01/test_events.py",
            "content": "def test_a():\n    assert True\n",
        }),
    )
    client = FakeClient(replies=[_reply(tool_calls=[edit]), _reply(tool_calls=[_finish_call("done")])])

    patch = run_fixer(_contract(_c), _c, ws, client, _settings(), Trace(tmp_path / 'tr.jsonl'))
    assert patch.touched_tests is True


def test_sandbox_trace_is_not_written_into_the_host_workspace(tmp_path):
    """A trace inside the tree lands in every patch, and in a judge workspace it
    would hold gold-test output where an agent could read it."""
    ws = _host_workspace(tmp_path)
    _c = Case(id='issue-01', title='t', issue_text='x', fixture='eventpulse')
    sandbox._trace_event(ws, ["docker", "run"], 0, 0.1, "out", "")

    assert not (ws.path / "sandbox.jsonl").exists()
    assert (ws.path.parent / f"{ws.path.name}.sandbox.jsonl").exists()
    assert "sandbox.jsonl" not in ws.snapshot_diff()
