# SplitSpec Review Packet — Issue issue-05

## Decision
ACCEPT

Decision inputs:
- Contract confidence: high
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: PASS (valid: True; ran: True)
- Patch edited an existing test: False

## Issue
Cross-user ticket access

I can view other people's tickets. When I request a ticket that one of my
teammates was issued, the API returns its full details instead of refusing
me. I was able to read the code of a co-worker's ticket by guessing its id,
which means ticket barcodes are effectively public. Each user should only be
able to read tickets issued to them.

- Out of scope: Ticket creation, updating, deletion, payment processing, barcode generation, and any behavior of other routes.

## Behavioral invariant
- When an authenticated user requests a ticket that they do not own, the API must not return the ticket's details.

## Candidate patch
- Files changed: app/routes/tickets.py, test_manual_verification.py, visible_tests/issue-05/test_cross_user_access.py
- Patch size: +82/-0 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed cross-user ticket access vulnerability by adding user ownership check in the ticket retrieval endpoint. Modified `app/routes/tickets.py` to verify that the authenticated user owns the requested ticket before returning details. Added test file `visible_tests/issue-05/test_cross_user_access.py` to verify the fix. All tests pass - users can access their own tickets but get 404 errors when trying to access other users' tickets, with no ticket details disclosed.

## Visible tests
PASS - 3 tests, 0 failed, 0 errors
```
...                                                                      [100%]
3 passed in 0.06s
```

## Independent verifier test
PASS - 1 tests, 0 failed, 0 errors
- Invariant: When an authenticated user requests a ticket that they do not own, the API must not return the ticket's details and should return a 403 Forbidden or 404 Not Found error.
- Assumptions:
  - The test assumes that ticket 1 is owned by a user other than 'bob' (specifically, it is owned by 'alice').
  - The test assumes the existence of 'alice' and 'bob' in the test database.
  - The test assumes authentication tokens are correctly provided.
- Validity: valid (compiles=True, runs=True, fails_on_original_bug=True) — test failed on the buggy code (1 failures) as expected

## Gold hidden evaluator
FAIL - 3 tests, 2 failed, 0 errors

## Mutation sensitivity
Detected 2/4 incorrect variants. A below-ceiling score may reflect a mutant no in-process test can kill (a manifest ceiling), not a test failure.
- Killed: 2/4

## Residual risks
- Out of scope (unaddressed): Ticket creation, updating, deletion, payment processing, barcode generation, and any behavior of other routes.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.