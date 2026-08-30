# SplitSpec Review Packet — Issue issue-03

## Decision
REVIEW REQUIRED

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Time-zone conversion

Events saved from timezones with a non-zero offset come back at the wrong
time. I scheduled an event for 10:00 in a GMT+2 office and the API reports
it as 10:00 UTC, so the start time shown on the page is two hours off from
what the organizer entered. Events entered in UTC are fine, so it only
starts to drift once an offset is involved.

- Out of scope: Client‑side rendering or formatting of the date string., Support for other date‑time fields unrelated to event start_time., Migration of existing data that may already be stored incorrectly.

## Behavioral invariant
- When an event is created with a start_time that includes a non‑zero timezone offset, the system must store the corresponding UTC instant (i.e., start_time_UTC = start_time_local minus the offset).
- When an event is retrieved, the reported start_time must represent the same absolute instant as the value supplied at creation; for inputs with an offset this typically means the API returns the UTC equivalent of the original local time.
- When an event is created with a start_time already expressed in UTC, the stored and returned value must be unchanged.

## Candidate patch
- Files changed: app/routes/events.py, visible_tests/issue-03/test_issue_examples.py, visible_tests/issue-03/test_timezone_edge_cases.py, visible_tests/issue-03/test_timezone_offset.py
- Patch size: +177/-2 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed timezone conversion issue in event creation by replacing `payload.starts_at.replace(tzinfo=None)` with `to_utc_naive(payload.starts_at)` in `app/routes/events.py`. This ensures that datetime inputs with timezone offsets are properly converted to UTC before storage. All existing tests pass, and new tests confirm correct handling of various timezone offsets including the specific examples from the issue description.

## Visible tests
PASS - 2 tests, 0 failed, 0 errors
```
..                                                                       [100%]
2 passed in 0.04s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
PASS - 1 tests, 0 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: Whether the API is required to return the start_time in UTC or preserve the original offset in the response.
- Contract ambiguity: Exact format of the date‑time string expected by the API (ISO‑8601, epoch milliseconds, etc.).
- Contract ambiguity: How naive (timezone‑less) datetime inputs should be interpreted.
- Out of scope (unaddressed): Client‑side rendering or formatting of the date string.
- Out of scope (unaddressed): Support for other date‑time fields unrelated to event start_time.
- Out of scope (unaddressed): Migration of existing data that may already be stored incorrectly.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.