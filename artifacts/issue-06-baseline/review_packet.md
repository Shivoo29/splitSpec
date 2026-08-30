# SplitSpec Review Packet — Issue issue-06

## Decision
REVIEW REQUIRED

Decision inputs:
- Contract confidence: high
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Missing ownership check on cancellation

I cancelled a booking I never made and the system let me. I sent a cancel
request for a registration id that was not mine and instead of being told I
did not own it, the other person's booking was cancelled. Nobody should be
able to cancel a registration that does not belong to them, and a rejected
cancellation should leave the booking completely unchanged.

- Out of scope: Creation, update, or deletion of registrations other than cancellation., Payment processing, event management, ticket issuance, caching, or any unrelated API endpoints.

## Behavioral invariant
- The CancelRegistration operation must verify that the requester is the owner of the registration identified by the request.
- If the requester is not the owner, the operation must not modify any data of the registration and must return an error indicating insufficient permission.

## Candidate patch
- Files changed: app/routes/registrations.py, visible_tests/issue-06/test_cancel_ownership.py
- Patch size: +20/-0 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed missing ownership check on registration cancellation by adding a simple user ID verification in the cancel endpoint. The fix ensures that only the owner of a registration can cancel it, returning HTTP 403 Forbidden for unauthorized attempts while leaving the registration data completely unchanged. All existing tests pass, and a new test was added to verify the ownership check works correctly.

## Visible tests
PASS - 5 tests, 0 failed, 0 errors
```
.....                                                                    [100%]
5 passed in 0.09s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
PASS - 2 tests, 0 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Out of scope (unaddressed): Creation, update, or deletion of registrations other than cancellation.
- Out of scope (unaddressed): Payment processing, event management, ticket issuance, caching, or any unrelated API endpoints.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.