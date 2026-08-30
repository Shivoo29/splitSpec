# SplitSpec Review Packet — Issue issue-06

## Decision
ACCEPT

Decision inputs:
- Contract confidence: high
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: PASS (valid: True; ran: True)
- Patch edited an existing test: False

## Issue
Missing ownership check on cancellation

I cancelled a booking I never made and the system let me. I sent a cancel
request for a registration id that was not mine and instead of being told I
did not own it, the other person's booking was cancelled. Nobody should be
able to cancel a registration that does not belong to them, and a rejected
cancellation should leave the booking completely unchanged.

- Out of scope: Cancellation of registrations owned by the requester., Behavior of admin or privileged roles that may be allowed to cancel any registration., Creation, payment, or other non‑cancellation endpoints.

## Behavioral invariant
- The system must verify that the authenticated user owns the registration identified in a cancellation request before performing any state change.
- If the user does not own the registration, the cancellation request must be rejected and the registration's state must remain unchanged.

## Candidate patch
- Files changed: app/routes/registrations.py, visible_tests/issue-06/test_cancel_comprehensive.py, visible_tests/issue-06/test_cancel_ownership.py
- Patch size: +78/-0 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; ## Summary I successfully fixed the missing ownership check on registration cancellation in the EventPulse application. ### Changes Made **File Modified:** `app/routes/registrations.py` **Change:** Added an ownership check in the `cancel` endpoint to ensure that users can only cancel their own registrations. ```python @router.delete("/{registration_id}", response_model=RegistrationOut) def cancel( registration_id: int, request: Request, user: User = Depends(get_current_user), # noqa: B008 session: Session = Depends(get_session), # noqa: B008 ) -> dict: reg = session.get(Registration, registrat... [truncated, 2089 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 5 tests, 0 failed, 0 errors
```
.....                                                                    [100%]
5 passed in 0.09s
```

## Independent verifier test
PASS - 1 tests, 0 failed, 0 errors
- Invariant: A cancellation request for a registration must be rejected if the authenticated user is not the owner of that registration, and the registration must remain in its original state.
- Assumptions:
  - Registration ID 3 is initially owned by Alice (User ID 1) and its status is 'confirmed'.
  - Bob is a valid user (User ID 2) who is authenticated but does not own registration ID 3.
  - The system rejects non-authorized attempts with a status code other than 200 (e.g., 403).
- Validity: valid (compiles=True, runs=True, fails_on_original_bug=True) — test failed on the buggy code (1 failures) as expected

## Gold hidden evaluator
PASS - 2 tests, 0 failed, 0 errors

## Mutation sensitivity
Detected 3/4 incorrect variants. A below-ceiling score may reflect a mutant no in-process test can kill (a manifest ceiling), not a test failure.
- Killed: 3/4

## Residual risks
- Contract ambiguity: Exact HTTP status code or error payload that should be returned on ownership failure.
- Contract ambiguity: Whether there are any roles (e.g., admin) that are permitted to cancel registrations they do not own.
- Contract ambiguity: Specific audit‑logging requirements for rejected cancellation attempts.
- Out of scope (unaddressed): Cancellation of registrations owned by the requester.
- Out of scope (unaddressed): Behavior of admin or privileged roles that may be allowed to cancel any registration.
- Out of scope (unaddressed): Creation, payment, or other non‑cancellation endpoints.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.