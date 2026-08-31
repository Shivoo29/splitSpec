# SplitSpec Review Packet — Issue issue-01

## Decision
REVIEW REQUIRED

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Null / empty-value validation

When I create an event through our public API it succeeds even for data that
should never be allowed. I just created an event with an empty title and
another with a negative ticket price, and both came back as created and now
show up in the event listing. Our frontend depends on the API rejecting
these before they exist, so I am worried bad data is piling up.

- Out of scope: Validation of other fields not mentioned in the report (e.g., description, date, location)., Authentication/authorization behavior for the endpoint., Behaviour of the API for completely missing fields versus empty strings., Database schema constraints unrelated to the described validation.

## Behavioral invariant
- Creating an event with an empty title must be rejected by the API and must not result in a persisted event.
- Creating an event with a negative ticket price must be rejected by the API and must not result in a persisted event.

## Candidate patch
- Files changed: app/routes/events.py, final_validation_test.py, test_edge_cases.py, test_validation.py
- Patch size: +168/-0 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; ## Summary I successfully resolved the validation issue in the EventPulse API by adding input validation to the `EventCreate` Pydantic model in `app/routes/events.py`. ### Changes Made **File: `app/routes/events.py`** - Added a field validator `_check_title_not_empty` that rejects empty or whitespace-only titles - Added a field validator `_check_price_non_negative` that rejects negative prices - Both validators raise `ValueError` with descriptive error messages when validation fails ### Validation Behavior 1. **Empty Title Validation**: The API now rejects event creation requests with empty or... [truncated, 1532 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 4 tests, 0 failed, 0 errors
```
....                                                                     [100%]
4 passed in 0.07s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
FAIL - 3 tests, 2 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: Exact HTTP status code to be used for validation failures (e.g., 400 vs 422).
- Contract ambiguity: Exact structure and content of the error response payload (JSON schema, error codes, messages).
- Contract ambiguity: Whether a missing title field should be treated the same as an empty string.
- Contract ambiguity: Whether zero ticket price is considered valid or should also be rejected.
- Out of scope (unaddressed): Validation of other fields not mentioned in the report (e.g., description, date, location).
- Out of scope (unaddressed): Authentication/authorization behavior for the endpoint.
- Out of scope (unaddressed): Behaviour of the API for completely missing fields versus empty strings.
- Out of scope (unaddressed): Database schema constraints unrelated to the described validation.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.