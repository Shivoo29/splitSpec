"""Render a run's trajectory.jsonl into a readable Markdown transcript.

    python scripts/render_trajectory.py artifacts/issue-01-splitspec

`trajectory.jsonl` is the audit record: one JSON object per event, append-only,
written by every stage. It is complete but not readable, and the hackathon asks
for trajectories a person can follow "from the agent instructions to the final
result". This turns one into that, without inventing anything the trace does not
already contain.

Deliberately shows, because these are the things a reader needs to judge a run:

- the system prompt each agent actually received (from splitspec/prompts/),
- every model call with its token counts and finish reason,
- every tool call and, critically, every tool ERROR - a tool that failed is the
  feedback that shaped the agent's next step,
- the retry/stop reason, so a truncated attempt is never mistaken for a finished one,
- the validity gate's verdict with its stated reason,
- the three suites in fixed order, and the final decision.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "splitspec" / "prompts"


def _events(run_dir: Path) -> list[dict]:
    path = run_dir / "trajectory.jsonl"
    if not path.is_file():
        raise SystemExit(f"no trajectory.jsonl in {run_dir}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fmt_tool(event: dict) -> str:
    """One line per tool call. Errors are called out, not folded in with successes."""
    tool = event.get("tool", "?")
    if event["kind"] == "tool_error":
        return f"  - **`{tool}` FAILED** — {event.get('reason')}: `{event.get('detail')}`"
    detail = event.get("path") or event.get("pattern") or ""
    extra = []
    if "exit_code" in event:
        extra.append(f"exit={event['exit_code']}")
    if "chars" in event:
        extra.append(f"{event['chars']} chars")
    if "entries" in event:
        extra.append(f"{event['entries']} entries")
    suffix = f" ({', '.join(extra)})" if extra else ""
    return f"  - `{tool}` {detail}{suffix}".rstrip()


def _agent_section(out: list[str], events: list[dict], role: str, prompt_file: str) -> None:
    role_events = [e for e in events if e["actor"] == role]
    if not role_events:
        return

    out.append(f"## {role.title()} agent\n")

    prompt = PROMPTS / prompt_file
    if prompt.is_file():
        text = prompt.read_text(encoding="utf-8").strip()
        out.append("<details><summary>System prompt (instructions this agent received)</summary>\n")
        out.append(f"```\n{text}\n```\n")
        out.append("</details>\n")

    calls = [e for e in role_events if e["kind"] == "model_call"]
    end = next((e for e in role_events if e["kind"] == "agent_end"), None)

    if end:
        stop = end["stop_reason"]
        flag = "" if stop == "finished" else "  ← **not a completed attempt**"
        out.append(
            f"**{len(calls)} model calls · stop_reason `{stop}`{flag} · "
            f"{end.get('tokens_generated', 0)} tokens generated, "
            f"{end.get('billed_tokens', 0)} billed**\n"
        )

    # Interleave model calls and the tool calls they produced, in trace order.
    out.append("### Turns\n")
    turn = 0
    for event in role_events:
        if event["kind"] == "model_call":
            turn += 1
            out.append(
                f"**Turn {turn}** — in {event['input_tokens']} / out {event['output_tokens']} tokens, "
                f"finish `{event['finish_reason']}`, {event['tool_calls']} tool call(s)"
            )
        elif event["kind"] in {"tool_call", "tool_error"}:
            out.append(_fmt_tool(event))
    out.append("")

    for event in role_events:
        if event["kind"] == "patch":
            out.append(
                f"**Result:** patch touching {event['files']}, "
                f"+{event['lines_added']}/-{event['lines_removed']}, "
                f"edited an existing test: {event['touched_tests']}\n"
            )
        if event["kind"] == "test":
            out.append(f"**Result:** `{event['filename']}` — confidence {event['confidence']}\n")
            out.append(f"> {event['invariant']}\n")


def render(run_dir: Path) -> str:
    events = _events(run_dir)
    out: list[str] = [f"# Trajectory — {run_dir.name}\n"]

    report = next((e for e in events if e["kind"] == "written"), None)
    if report:
        models = ", ".join(f"{r}={m}" for r, m in report.get("models", []))
        out.append(
            f"`{report['case_id']}` · mode `{report['mode']}` · {models} · "
            f"{report['runtime_sec']:.0f}s\n"
        )

    contract = next((e for e in events if e["kind"] == "parsed"), None)
    if contract:
        out.append("## Contract builder\n")
        out.append(
            f"Produced {contract['n_invariants']} invariant(s) and "
            f"{contract['n_ambiguities']} ambiguity/ies at **{contract['confidence']}** confidence. "
            "A low-confidence contract escalates the run instead of proceeding.\n"
        )

    # Fixer and verifier ran on separate workspaces and never saw each other's output;
    # they are presented apart for the same reason.
    _agent_section(out, events, "fixer", "fixer.md")
    _agent_section(out, events, "verifier", "verifier.md")

    freeze = next((e for e in events if e["kind"] == "freeze"), None)
    if freeze:
        out.append("## Freeze\n")
        out.append(
            f"`{freeze['filename']}` hashed as `{freeze['frozen_sha256'][:16]}…` before any "
            "patch was judged. The judge re-hashes it; a mismatch aborts the run.\n"
        )

    gate = next((e for e in events if e["kind"] == "validity"), None)
    if gate:
        verdict = "VALID" if gate["passed"] else "INVALID"
        out.append("## Validity gate\n")
        if gate.get("skipped"):
            # Case 11 has no seeded bug, so there is nothing for a test to catch and
            # the three booleans are absent rather than false: missing, not negative.
            out.append(f"**{verdict}** - not assessed ({gate['skipped']})\n")
        else:
            out.append(
                f"**{verdict}** - compiles={gate.get('compiles')}, runs={gate.get('runs')}, "
                f"fails_on_original_bug={gate.get('fails_on_original_bug')}\n"
            )
        out.append(f"> {gate.get('reason', 'no reason recorded')}\n")

    suites = [e for e in events if e["kind"] == "suite"]
    if suites:
        out.append("## Judge\n")
        out.append("| Suite | Result | Tests | Failed | Errors | Seconds |")
        out.append("|---|---|---|---|---|---|")
        for s in suites:
            out.append(
                f"| {s['label']} | {'PASS' if s['passed'] else 'FAIL'} | {s['total']} | "
                f"{s['failures']} | {s['errors']} | {s['duration_sec']:.1f} |"
            )
        out.append("")

    mutation = next((e for e in events if e["kind"] == "score"), None)
    if mutation:
        out.append("## Mutation sensitivity\n")
        excluded = mutation.get("excluded_unkillable") or []
        note = f" ({', '.join(excluded)} excluded as unkillable in-process)" if excluded else ""
        out.append(
            f"Killed **{mutation['killed']}/{mutation['denominator']}** scored mutants{note}.\n"
        )

    out.append("---\n")
    out.append(
        "SplitSpec merged nothing and approved nothing. Every decision above is advisory "
        "evidence for a human reviewer.\n"
    )
    return "\n".join(out)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for arg in sys.argv[1:]:
        run_dir = Path(arg)
        text = render(run_dir)
        out_path = run_dir / "trajectory.md"
        out_path.write_text(text, encoding="utf-8")
        print(f"wrote {out_path} ({len(text)} chars)")


if __name__ == "__main__":
    main()
