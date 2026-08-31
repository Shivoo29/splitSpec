# SplitSpec Review Packet — Issue issue-11

## Decision
ESCALATE

Decision inputs:
- Contract confidence: low
- Expect escalation (case rule): True
- Visible tests: FAIL (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Registrations occasionally disappear

Something is wrong with registrations. A user told us on Monday that their
registration was "gone", but when we looked at the account it was there. Our
support lead thinks she saw the same thing last month on a different account
but she is not sure it was the same problem. It might be related to the
mobile app, or to the email confirmations, we are not certain which. We do
not have the account id or a timestamp any more. Nobody has been able to make
it happen on purpose. Please fix.


## Behavioral invariant
None captured — the contract was not produced (or was unreadable).
## Candidate patch
- Files changed: app/routes/registrations.py, test_basic.py, test_simple.py, visible_tests/issue-11/test_race_condition.py, visible_tests/issue-11/test_simple.py
- Patch size: +124/-1 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; I analyzed the issue of registrations occasionally disappearing and identified a race condition in the registration reactivation logic. The problem occurred when multiple concurrent requests tried to reactivate the same cancelled registration, potentially leading to inconsistent states. ## Changes Made **File: `app/routes/registrations.py`** - Added a second status check right before updating an existing cancelled registration - This prevents race conditions where another request might have already reactivated the registration - If the registration status is already "confirmed" when we're abou... [truncated, 1606 chars; full reply in trajectory.jsonl]

## Visible tests
FAIL - 0 tests, 0 failed, 0 errors

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
FAIL - 0 tests, 0 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: No deterministic steps to reproduce the disappearance are provided.
- Contract ambiguity: Missing specific account identifier(s) or registration ID(s).
- Contract ambiguity: No timestamp or time window indicating when the issue occurred.
- Contract ambiguity: Unclear which API endpoint or UI action is involved (e.g., mobile app, email confirmation, web UI).
- Contract ambiguity: Uncertain whether the disappearance is permanent or temporary, and what the expected persistence behavior is.
- Case is marked expect_escalation; it is scored on whether the run escalated, not on patch correctness.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.