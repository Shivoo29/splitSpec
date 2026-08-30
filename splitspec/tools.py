"""Agent tool loop (Module 5).

:func:`run_agent` drives a scripted conversation against one model client inside
one Module 3 :class:`~splitspec.sandbox.Workspace`. The model proposes tool calls,
the loop executes them against the workspace, feeds the results back, and stops on
the ``finish`` tool, a plain final message, budget exhaustion, a truncated
(``length``) reply, or an empty (reasoning-budget-exhausted) reply.

The loop owns nothing about fixing or verifying: it receives the system prompt and
tools and returns an :class:`AgentResult`. Every model call and tool call is written
to the run :class:`~splitspec.trace.Trace` with token usage; an API key never is.

The agent's tool loop runs for both the fixer and the verifier; the six tools below
are scoped to exactly one workspace and ``run_tests`` only ever runs plain
``pytest`` invocations in the sandbox and never receives the gold-test mount.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from splitspec.config import Settings
from splitspec.llm import ModelClient, ToolCall
from splitspec.sandbox import PathEscape, Workspace, run_in_sandbox
from splitspec.schemas import ModelUse
from splitspec.trace import Trace

FINISH_TOOL = "finish"

_MAX_TURNS = 100
# Per-reply ceiling. Reasoning models need real headroom here or they spend the whole
# allowance thinking and return an empty message; the run-wide cap is
# Settings.max_tokens_per_agent, which is a different quantity entirely.
_MAX_TOKENS_PER_REPLY = 8000
_READ_CAP_CHARS = 20_000
_SEARCH_CAP_MATCHES = 200
_RUN_TESTS_TIMEOUT_CAP_SEC = 180

# Characters that would let a tool argument smuggle shell semantics; plain pytest
# tokens never need them.
_RUN_TESTS_METACHARS = set(";&|`$<>")

STOP_FINISHED = "finished"
STOP_BUDGET = "budget"
STOP_LENGTH = "length"
STOP_EMPTY = "empty_response"
STOP_MAX_TURNS = "max_turns"


@dataclass
class ToolContext:
    """Everything a tool needs at runtime: its workspace, the run trace, settings."""

    workspace: Workspace
    trace: Trace
    settings: Settings


ToolFn = Callable[[ToolContext, dict[str, Any]], str]


@dataclass(frozen=True)
class ToolSpec:
    """One workspace-scoped tool: its OpenAI schema plus the Adder of its effect."""

    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn

    def as_api_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class AgentResult:
    """What a finished agent loop produced, with the role's final usage."""

    def __init__(
        self,
        final_message: str,
        stop_reason: str,
        model_use: ModelUse,
        tool_calls: list[dict],
        messages: list[dict],
    ) -> None:
        self.final_message = final_message
        self.stop_reason = stop_reason
        self.model_use = model_use
        self.tool_calls = tool_calls
        self.messages = messages


# --- parsing + guard helpers -------------------------------------------------


def _strip_code_fence(text: str) -> str:
    """Return the JSON body of a fenced reply (```json ... ```)."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    without_open = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    closing = without_open.rfind("```")
    return (without_open[:closing] if closing != -1 else without_open).strip()


def _parse_args(raw: str) -> dict[str, Any]:
    data = json.loads(_strip_code_fence(raw))
    if not isinstance(data, dict):
        raise ValueError("tool arguments must be a JSON object")
    return data


def _guard_workspace(workspace: Workspace, dst: str) -> Path:
    """Resolve ``dst`` and refuse anything outside the workspace root."""
    root = Path(workspace.path).resolve()
    try:
        resolved = Path(dst).resolve(strict=False)
    except OSError as exc:  # pragma: no cover - defensive
        raise PathEscape(str(dst)) from exc
    if not (resolved == root or root in resolved.parents):
        raise PathEscape(str(dst))
    return resolved


def _tool_error(ctx: ToolContext, tool: str, reason: str, detail: Any) -> str:
    ctx.trace.event(
        ctx.workspace.role, "tool_error", tool=tool, reason=reason,
        detail=_plain(detail),
    )
    return f"ERROR: {tool}: {reason}: {detail}"


def _plain(value: Any) -> str:
    return value if isinstance(value, str) else repr(value)


# --- the six tools -----------------------------------------------------------


def tool_list_files(ctx: ToolContext, args: dict[str, Any]) -> str:
    rel = _plain(args.get("path") or ".")
    base = Path(ctx.workspace.path)
    try:
        target = _guard_workspace(ctx.workspace, str(base / rel))
    except PathEscape as exc:
        return _tool_error(ctx, "list_files", "path_escape", str(exc))
    if target.is_file():
        out = target.relative_to(base).as_posix()
    elif not target.is_dir():
        return _tool_error(ctx, "list_files", "not_found", rel)
    else:
        lines = [
            item.relative_to(base).as_posix() + ("/" if item.is_dir() else "")
            for item in sorted(target.rglob("*"))
        ]
        out = "\n".join(lines) if lines else "(empty directory)"
    ctx.trace.event(
        ctx.workspace.role, "tool_call", tool="list_files", path=rel,
        entries=len(out.splitlines()),
    )
    return out


def tool_read_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    rel = _plain(args.get("path") or "")
    base = Path(ctx.workspace.path)
    try:
        target = _guard_workspace(ctx.workspace, str(base / rel))
    except PathEscape as exc:
        return _tool_error(ctx, "read_file", "path_escape", str(exc))
    if not target.is_file():
        return _tool_error(ctx, "read_file", "not_found", rel)
    text = target.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > _READ_CAP_CHARS
    body = text[:_READ_CAP_CHARS]
    if truncated:
        body += f"\n... (truncated at {_READ_CAP_CHARS} chars)"
    ctx.trace.event(
        ctx.workspace.role, "tool_call", tool="read_file", path=rel,
        chars=len(text), truncated=truncated,
    )
    return body


def tool_write_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    rel = _plain(args.get("path") or "")
    content = _plain(args.get("content") or "")
    base = Path(ctx.workspace.path)
    try:
        target = _guard_workspace(ctx.workspace, str(base / rel))
    except PathEscape as exc:
        return _tool_error(ctx, "write_file", "path_escape", str(exc))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    ctx.trace.event(
        ctx.workspace.role, "tool_call", tool="write_file", path=rel, chars=len(content),
    )
    return f"wrote {len(content)} chars to {rel}"


def tool_search(ctx: ToolContext, args: dict[str, Any]) -> str:
    pattern = _plain(args.get("pattern") or "")
    rel = _plain(args.get("path") or ".")
    base = Path(ctx.workspace.path)
    try:
        target = _guard_workspace(ctx.workspace, str(base / rel))
    except PathEscape as exc:
        return _tool_error(ctx, "search", "path_escape", str(exc))
    if not target.is_dir():
        return _tool_error(ctx, "search", "not_found", rel)
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return _tool_error(ctx, "search", "bad_pattern", str(exc))

    matches: list[str] = []
    for item in sorted(target.rglob("*")):
        if not item.is_file():
            continue
        try:
            text = item.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover - unreadable file
            continue
        for lineno, line in enumerate(text.splitlines() or [""], 1):
            if rx.search(line):
                matches.append(f"{item.relative_to(base).as_posix()}:{lineno}: {line}")
                if len(matches) >= _SEARCH_CAP_MATCHES:
                    break
        if len(matches) >= _SEARCH_CAP_MATCHES:
            break
    ctx.trace.event(
        ctx.workspace.role, "tool_call", tool="search", pattern=pattern,
        matches=len(matches),
    )
    return "\n".join(matches) if matches else "(no matches)"


def tool_run_tests(ctx: ToolContext, args: dict[str, Any]) -> str:
    raw = args.get("command")
    if not isinstance(raw, list) or not raw or not all(isinstance(x, str) for x in raw):
        return _tool_error(ctx, "run_tests", "bad_command", raw)
    command = list(raw)
    if command[0] != "pytest":
        return _tool_error(
            ctx, "run_tests", "refused", "only 'pytest' invocations are allowed"
        )
    for token in command:
        if any(c in token for c in _RUN_TESTS_METACHARS):
            return _tool_error(
                ctx, "run_tests", "refused", f"disallowed characters in {token!r}"
            )

    # The sandbox mounts only the workspace; gold tests are never passed here.
    timeout = min(ctx.settings.agent_timeout_sec, _RUN_TESTS_TIMEOUT_CAP_SEC)
    result = run_in_sandbox(ctx.workspace, command, timeout)
    ctx.trace.event(
        ctx.workspace.role, "tool_call", tool="run_tests", command=list(command),
        exit_code=result.exit_code, duration_sec=round(result.duration_sec, 3),
    )
    tail = (result.stdout or "")[-2000:]
    return f"exit={result.exit_code} duration={result.duration_sec:.1f}s\n" + tail


def tool_finish(ctx: ToolContext, args: dict[str, Any]) -> str:
    summary = _plain(args.get("summary") or "")
    ctx.trace.event(ctx.workspace.role, "tool_call", tool="finish", chars=len(summary))
    return summary


def default_tools() -> list[ToolSpec]:
    """The six workspace-scoped tools the fixer and verifier share."""
    return [
        ToolSpec(
            "list_files",
            "List files under a directory in the workspace (default '.').",
            {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "directory"}},
            },
            tool_list_files,
        ),
        ToolSpec(
            "read_file",
            "Read the contents of a file in the workspace.",
            {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "file path"}},
                "required": ["path"],
            },
            tool_read_file,
        ),
        ToolSpec(
            "write_file",
            "Write content to a file in the workspace, creating parent dirs.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "file path"},
                    "content": {"type": "string", "description": "file contents"},
                },
                "required": ["path", "content"],
            },
            tool_write_file,
        ),
        ToolSpec(
            "search",
            "Regex search file contents under a directory in the workspace.",
            {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "regex"},
                    "path": {"type": "string", "description": "directory"},
                },
                "required": ["pattern"],
            },
            tool_search,
        ),
        ToolSpec(
            "run_tests",
            "Run a pytest invocation in the sandbox against the workspace.",
            {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "e.g. [\"pytest\", \"-q\"]",
                    }
                },
                "required": ["command"],
            },
            tool_run_tests,
        ),
        ToolSpec(
            FINISH_TOOL,
            "Report the final answer and stop the agent loop.",
            {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
            tool_finish,
        ),
    ]


# --- the loop ----------------------------------------------------------------


def _execute_tool(
    tc: ToolCall,
    by_name: dict[str, ToolSpec],
    ctx: ToolContext,
    made: list[dict],
) -> tuple[str, bool]:
    """Run one tool call; the bool is True when it was the finishing call."""
    if tc.name == FINISH_TOOL:
        try:
            args = _parse_args(tc.arguments)
        except (json.JSONDecodeError, ValueError) as exc:
            made.append({"name": tc.name, "error": True})
            return _tool_error(ctx, tc.name, "bad_args", str(exc)), False
        made.append({"name": tc.name, "args": args, "finish": True})
        return tool_finish(ctx, args), True

    tool = by_name.get(tc.name)
    if tool is None:
        made.append({"name": tc.name, "error": True, "unknown": True})
        return _tool_error(ctx, tc.name or "?", "unknown_tool", tc.name or ""), False

    try:
        args = _parse_args(tc.arguments)
    except (json.JSONDecodeError, ValueError) as exc:
        made.append({"name": tc.name, "error": True})
        return _tool_error(ctx, tc.name, "bad_args", str(exc)), False

    made.append({"name": tc.name, "args": args})
    return tool.fn(ctx, args), False


#: Default opening user turn so the loop always starts from a concrete instruction.
_DEFAULT_STARTER = "Work through the task in this workspace using the tools provided."


def run_agent(
    system_prompt: str,
    tools: list[ToolSpec],
    workspace: Workspace,
    client: ModelClient,
    settings: Settings,
    trace: Trace,
    role: str,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> AgentResult:
    """Run the agent loop to completion inside ``workspace``.

    Never raises on budget/empty/length exhaustion: it returns a partial
    :class:`AgentResult` with a non-``finished`` ``stop_reason`` instead.
    Repeated 429s are resolved by the client itself (rotation then backoff) and
    are *not* re-retried here.
    """
    by_name = {t.name: t for t in tools}
    provider = settings.provider(role)
    model_use = ModelUse(
        role=role, base_url=provider.base_url, model=provider.model,
    )
    ctx = ToolContext(workspace=workspace, trace=trace, settings=settings)

    messages: list[dict] = [{"role": "user", "content": _DEFAULT_STARTER}]
    api_tools = [t.as_api_schema() for t in tools]
    made: list[dict] = []

    # The budget counts GENERATED tokens, not billed tokens. Every turn resends the
    # whole transcript, so summing each reply's input_tokens charges the same context
    # again on every turn: a real run reached turn 22 with a 19k transcript having
    # "used" 205k of a 200k budget. That terminates agents on an accounting artifact
    # rather than on work done, and it makes the results measure the budget instead
    # of the model. Billed totals are still recorded in full on model_use, which is
    # what the cost metric reads; _MAX_TURNS remains the leash on a runaway loop.
    token_budget = settings.max_tokens_per_agent
    tokens_generated = 0
    start = clock()

    stop_reason = STOP_FINISHED
    final_message = ""

    for _turn in range(_MAX_TURNS):
        elapsed = clock() - start
        if tokens_generated >= token_budget or elapsed >= settings.agent_timeout_sec:
            stop_reason = STOP_BUDGET
            trace.event(
                role, "budget", reason="budget_exceeded",
                tokens_generated=tokens_generated,
                billed_tokens=model_use.input_tokens + model_use.output_tokens,
                token_budget=token_budget, elapsed_sec=round(elapsed, 3),
            )
            break

        # max_tokens caps ONE reply, not the run. Sending the whole sweep budget is
        # rejected by providers whose per-response ceiling is far lower, and it lets a
        # single turn eat everything. Never ask for more than the run has left.
        reply = client.respond(
            system=system_prompt, messages=messages, tools=api_tools,
            max_tokens=max(1, min(_MAX_TOKENS_PER_REPLY, token_budget - tokens_generated)),
        )
        model_use.calls += 1
        model_use.input_tokens += reply.input_tokens
        model_use.output_tokens += reply.output_tokens
        tokens_generated += reply.output_tokens
        trace.event(
            role, "model_call", model=reply.model, input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens, finish_reason=reply.finish_reason,
            tool_calls=len(reply.tool_calls),
        )

        if reply.finish_reason == "length":
            # Truncation is reported as truncation, not as something parseable.
            stop_reason = STOP_LENGTH
            final_message = reply.text
            break
        if reply.empty:
            # A reasoning model that spent its whole budget returns HTTP 200 with
            # nothing at all; that is not a successful finish.
            stop_reason = STOP_EMPTY
            final_message = reply.text
            break
        if not reply.tool_calls:
            final_message = reply.text
            stop_reason = STOP_FINISHED
            break

        # The assistant turn must precede its tool results. A `role: "tool"` message
        # that does not answer an assistant message carrying the same tool_call_id is
        # rejected by every OpenAI-compatible provider, and a FakeClient cannot see it
        # because it never validates the transcript it is handed.
        messages.append(
            reply.raw_message
            or {
                "role": "assistant",
                "content": reply.text or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in reply.tool_calls
                ],
            }
        )

        finished = False
        for tc in reply.tool_calls:
            result, is_finish = _execute_tool(tc, by_name, ctx, made)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )
            if is_finish:
                final_message = result
                stop_reason = STOP_FINISHED
                finished = True
                break
        if finished:
            break
    else:
        # The _MAX_TURNS guard: a loop that never stopped is a resource problem.
        stop_reason = STOP_MAX_TURNS
        trace.event(role, "budget", reason="max_turns", turns=_MAX_TURNS)

    trace.event(
        role, "agent_end", stop_reason=stop_reason, final_message_len=len(final_message),
        calls=model_use.calls, tokens_generated=tokens_generated,
        billed_tokens=model_use.input_tokens + model_use.output_tokens,
    )
    return AgentResult(
        final_message=final_message,
        stop_reason=stop_reason,
        model_use=model_use,
        tool_calls=made,
        messages=messages,
    )
