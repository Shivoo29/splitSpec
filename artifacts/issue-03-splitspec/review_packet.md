# SplitSpec Review Packet — Issue issue-03

## Decision
ACCEPT

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: PASS (valid: True; ran: True)
- Patch edited an existing test: False

## Issue
Time-zone conversion

Events saved from timezones with a non-zero offset come back at the wrong
time. I scheduled an event for 10:00 in a GMT+2 office and the API reports
it as 10:00 UTC, so the start time shown on the page is two hours off from
what the organizer entered. Events entered in UTC are fine, so it only
starts to drift once an offset is involved.

- Out of scope: Client‑side rendering of the time on web pages., Handling of other event fields unrelated to start_time., Support for time zones other than UTC and the supplied offset beyond correct conversion.

## Behavioral invariant
- If an event is created with a start_time that includes a non‑zero offset (e.g., '+02:00'), the timestamp returned by the API for that event must represent the same absolute point in time as the value supplied (i.e., the offset must be honoured in storage and retrieval).
- The API must not reinterpret a timestamp with a non‑zero offset as if it were UTC; the returned value must either preserve the original offset or, if normalised to UTC, reflect the correct UTC equivalent.

## Candidate patch
- Files changed: app/routes/events.py, test_comprehensive_timezone.py, test_issue_fix.py, test_timezone_issue.py
- Patch size: +154/-2 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed timezone conversion issue (issue-03) by using the existing `to_utc_naive` utility function instead of `replace(tzinfo=None)` when storing event start times. This ensures that timestamps with non-zero timezone offsets are properly converted to UTC, eliminating the two-hour shift bug. Changed only one line in `app/routes/events.py` and added the necessary import. All existing tests pass.

## Visible tests
PASS - 2 tests, 0 failed, 0 errors
```
..                                                                       [100%]
2 passed in 0.05s
```

## Independent verifier test
PASS - 1 tests, 0 failed, 0 errors
- Invariant: The API must preserve the absolute point in time when a start_time with a timezone offset is provided. Conversion to UTC should correctly account for the offset, so that '10:00:00+02:00' becomes '08:00:00+00:00' rather than '10:00:00+00:00'.
- Assumptions:
  - The API is expected to handle ISO-8601 timestamps containing timezone offsets correctly.
  - The client-provided timestamp '2023-09-01T10:00:00+02:00' should be normalized to '2023-09-01T08:00:00+00:00' (or equivalent) in the storage/retrieval process.
  - The system supports and parses +02:00 offset in the incoming JSON.
- Validity: valid (compiles=True, runs=True, fails_on_original_bug=True) — test failed on the buggy code (1 failures) as expected

## Gold hidden evaluator
PASS - 1 tests, 0 failed, 0 errors

## Mutation sensitivity
Detected 4/4 incorrect variants
- Killed: 4/4

## Residual risks
- Contract ambiguity: The exact endpoint URLs, HTTP methods, and request/response payload schemas are not provided.
- Contract ambiguity: It is unclear whether the API is expected to return timestamps in UTC or preserve the original offset; the contract only requires that the absolute instant be correct.
- Contract ambiguity: The database schema and whether timestamps are stored as naive or timezone‑aware datetime objects are unspecified.
- Out of scope (unaddressed): Client‑side rendering of the time on web pages.
- Out of scope (unaddressed): Handling of other event fields unrelated to start_time.
- Out of scope (unaddressed): Support for time zones other than UTC and the supplied offset beyond correct conversion.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.