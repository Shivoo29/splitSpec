# SplitSpec Review Packet — Issue issue-02

## Decision
REVIEW REQUIRED

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Pagination off-by-one

When I page through the event listing a few records at a time, some events
show up on two consecutive pages and the ordering jumps around. Walking the
whole list by paging gives me a different sequence, with duplicates, than
fetching the whole list at once. I expected paging through everything to be
exactly the same as one big fetch, just broken into chunks.

- Out of scope: Changes to the underlying data (e.g., events being added, removed, or updated) between paginated requests., Performance characteristics of pagination (query speed, latency)., User interface rendering of the paginated data., Any filtering, search, or authorization logic not directly related to pagination.

## Behavioral invariant
- When fetching events with pagination parameters (e.g., limit/offset or page/size), each page must return a contiguous, non‑overlapping slice of the total ordered result set.
- The concatenation of all paginated pages, in page order, must be exactly the same ordered list as retrieving all events in one request without pagination.

## Candidate patch
- Files changed: app/routes/events.py, test_final_verification.py, test_pagination_comprehensive.py, test_pagination_issue.py, test_pagination_simple.py
- Patch size: +179/-1 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed pagination off-by-one error in app/routes/events.py by removing the `- 1` from the offset calculation (line 97). Changed `.offset(offset - 1)` to `.offset(offset)`. This ensures paginated results are contiguous, non-overlapping, and concatenate to match unpaginated results. All visible tests pass.

## Visible tests
PASS - 3 tests, 0 failed, 0 errors
```
...                                                                      [100%]
3 passed in 0.05s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
PASS - 2 tests, 0 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: Exact pagination mechanism used by the API (offset‑based vs page‑number‑based).
- Contract ambiguity: The default sorting key and direction applied to the event list.
- Contract ambiguity: Whether any hidden filters or default query parameters affect the result set.
- Contract ambiguity: The size of the dataset required to reliably reproduce the issue.
- Out of scope (unaddressed): Changes to the underlying data (e.g., events being added, removed, or updated) between paginated requests.
- Out of scope (unaddressed): Performance characteristics of pagination (query speed, latency).
- Out of scope (unaddressed): User interface rendering of the paginated data.
- Out of scope (unaddressed): Any filtering, search, or authorization logic not directly related to pagination.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.